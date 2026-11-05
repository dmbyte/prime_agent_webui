"""Narrow direct-broker ISO installation controls. No arbitrary HTTP or auto replay."""
import base64
import contextlib
import fcntl
import hashlib
import http.client
import ipaddress
import json
import os
import re
import ssl
from urllib.parse import urlsplit

from connection_approvals import Approvals
import connections
import skill_credentials as credentials

class InstallationPrecondition(ValueError):
    """Safe public message: no vendor response, target data or credentials."""


def nonce(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-f0-9]{32}', value):
        raise ValueError('Retain an explicit 32-hex request ID')


def image_url(value, target):
    if not isinstance(value, str) or len(value) > 1024:
        raise ValueError('Use a bounded unauthenticated LAN ISO URL')
    try:
        p = urlsplit(value)
        address = ipaddress.ip_address(p.hostname or '')
        port = p.port
        if (address.version != 4 or not any(address in n for n in connections.RFC1918)
                or p.scheme not in ('http', 'https') or p.username is not None or p.password is not None
                or p.query or p.fragment or p.hostname == urlsplit(target).hostname
                or not re.fullmatch(r'/[A-Za-z0-9_./-]+\.iso', p.path, re.I)
                or any(x in ('', '.', '..') for x in p.path.split('/')[1:])
                or p.netloc != str(address)+((':'+str(port)) if port is not None else '')
                or value != p.scheme+'://'+p.netloc+p.path or port is not None and not 1 <= port <= 65535):
            raise ValueError()
    except (ValueError, TypeError):
        raise ValueError('Use an exact private IPv4 HTTP(S) .iso URL without credentials, queries or traversal') from None
    return value


def validate(operation, arguments, target):
    if not isinstance(arguments, dict):
        raise ValueError('Arguments must be an object')
    fields = {'redfish.media.insert': {'requestId', 'systemId', 'mediaResource', 'imageUrl'},
              'redfish.media.eject': {'requestId', 'systemId', 'mediaResource'},
              'redfish.boot.once': {'requestId', 'systemId', 'mediaRequestId', 'mode'},
              'redfish.boot.restart': {'requestId', 'systemId', 'bootRequestId', 'resetType'}}
    if operation not in fields or set(arguments) != fields[operation]:
        raise ValueError('Unsupported installation operation or fields')
    nonce(arguments['requestId'])
    system = arguments['systemId']
    if not isinstance(system, str) or not re.fullmatch(connections.REDFISH_ID, system) or system in ('.', '..'):
        raise ValueError('Select an observed system ID')
    if 'mediaResource' in arguments:
        resource = arguments['mediaResource']
        if (not isinstance(resource, str) or not re.fullmatch(
                rf'/redfish/v1/(?:Systems|Managers)/{connections.REDFISH_ID}/VirtualMedia/{connections.REDFISH_ID}', resource)
                or any(x in ('.', '..') for x in resource.split('/'))):
            raise ValueError('Select an observed virtual media resource')
    if 'imageUrl' in arguments:
        image_url(arguments['imageUrl'], target)
    if operation == 'redfish.boot.once':
        nonce(arguments['mediaRequestId'])
        if arguments['mode'] not in ('UEFI', 'Legacy'):
            raise ValueError('Choose UEFI or Legacy explicitly')
    if operation == 'redfish.boot.restart':
        nonce(arguments['bootRequestId'])
        if arguments['resetType'] not in ('GracefulRestart', 'On'):
            raise ValueError('Only graceful restart or power-on is supported')


def etag(data):
    tag = data.get('@odata.etag')
    if not isinstance(tag, str) or not re.fullmatch(r'(?:W/)?"[\x21\x23-\x7e]{1,200}"', tag):
        raise InstallationPrecondition('BMC did not advertise a usable ETag; no change sent')
    return tag


def action(data, resource, name):
    actions = data.get('Actions')
    entry = actions.get('#'+name, {}) if isinstance(actions, dict) else {}
    expected = resource+'/Actions/'+name
    if not isinstance(entry, dict) or entry.get('target') not in (expected, expected+'/'):
        raise InstallationPrecondition('Standard action was not advertised at the selected resource; no change sent')
    return entry, entry['target']


def advertised(values, value):
    return isinstance(values, list) and len(values) <= 64 and value in values


def plan(operation, args, row, get, approvals, owner, claim, connection_id):
    system_path = '/redfish/v1/Systems/'+args['systemId']
    paths = connections.redfish_members(get('/redfish/v1/Systems'), '/redfish/v1/Systems')
    if system_path not in paths:
        raise InstallationPrecondition('Selected system is no longer advertised; no change sent')
    system = get(system_path)

    def media(resource):
        collection = resource.rsplit('/', 1)[0]
        parent = collection.rsplit('/', 1)[0]
        if parent == system_path:
            data = system
        else:
            links = system.get('Links', {})
            managers = connections.redfish_members({'Members': links.get('ManagedBy', [])}, '/redfish/v1/Managers')
            if parent not in managers:
                raise InstallationPrecondition('Media does not belong to the selected system; no change sent')
            data = get(parent)
        if data.get('VirtualMedia', {}).get('@odata.id') not in (collection, collection+'/'):
            raise InstallationPrecondition('Selected media collection is not advertised; no change sent')
        if resource not in connections.redfish_members(get(collection), collection):
            raise InstallationPrecondition('Selected media is not advertised; no change sent')
        result = get(resource)
        if not isinstance(result.get('MediaTypes'), list) or not any(t in ('CD', 'DVD') for t in result['MediaTypes']):
            raise InstallationPrecondition('Selected resource is not advertised as CD/DVD media; no change sent')
        return result

    def mounted(n):
        prior = approvals.acknowledged_arguments(owner, claim, connection_id, row, n, 'redfish.media.insert')
        if prior['systemId'] != args['systemId']:
            raise InstallationPrecondition('Media acknowledgement belongs to another system; no change sent')
        result = media(prior['mediaResource'])
        if result.get('Inserted') is not True or result.get('WriteProtected') is not True or result.get('Image') != prior['imageUrl']:
            raise InstallationPrecondition('Approved image is not currently mounted read-only; no boot change or restart sent')
        return prior, etag(result)

    evidence = []
    review = {'systemId': args['systemId']}
    if operation in ('redfish.media.insert', 'redfish.media.eject'):
        resource = args['mediaResource']; data = media(resource)
        if operation.endswith('insert'):
            if data.get('Inserted') is not False or data.get('Image') not in (None, ''):
                raise InstallationPrecondition('Media is occupied or unknown; no implicit replacement is allowed')
            _, path = action(data, resource, 'VirtualMedia.InsertMedia')
            body = {'Image': args['imageUrl'], 'Inserted': True, 'WriteProtected': True}
        else:
            if data.get('Inserted') is not True:
                raise InstallationPrecondition('Media is not known to be inserted; no change sent')
            _, path = action(data, resource, 'VirtualMedia.EjectMedia')
            body = {}
        method, tag = 'POST', etag(data)
    elif operation == 'redfish.boot.once':
        mount, media_tag = mounted(args['mediaRequestId']); evidence.append(media_tag)
        review.update(mediaResource=mount['mediaResource'], imageUrl=mount['imageUrl'], mode=args['mode'])
        boot = system.get('Boot', {})
        if (not isinstance(boot, dict)
                or not advertised(boot.get('BootSourceOverrideTarget@Redfish.AllowableValues'), 'Cd')
                or boot.get('BootSourceOverrideEnabled') not in ('Disabled', 'Once')
                or boot.get('BootSourceOverrideMode') not in ('UEFI', 'Legacy')):
            raise InstallationPrecondition('Standard optical one-time boot is not advertised; no change sent')
        method, path, tag = 'PATCH', system_path, etag(system)
        body = {'Boot': {'BootSourceOverrideEnabled': 'Once', 'BootSourceOverrideTarget': 'Cd',
                         'BootSourceOverrideMode': args['mode']}}
    else:
        prior = approvals.acknowledged_arguments(owner, claim, connection_id, row, args['bootRequestId'], 'redfish.boot.once')
        if prior['systemId'] != args['systemId']:
            raise InstallationPrecondition('Boot acknowledgement belongs to another system; no restart sent')
        mount, media_tag = mounted(prior['mediaRequestId']); evidence.append(media_tag)
        review.update(mediaResource=mount['mediaResource'], imageUrl=mount['imageUrl'], mode=prior['mode'])
        boot = system.get('Boot', {})
        if not isinstance(boot, dict) or any(boot.get(k) != v for k, v in {'BootSourceOverrideEnabled': 'Once',
                'BootSourceOverrideTarget': 'Cd', 'BootSourceOverrideMode': prior['mode']}.items()):
            raise InstallationPrecondition('One-time boot readback does not match the approved setting; no restart sent')
        entry, path = action(system, system_path, 'ComputerSystem.Reset')
        if (not advertised(entry.get('ResetType@Redfish.AllowableValues'), args['resetType'])
                or system.get('PowerState') != ('Off' if args['resetType'] == 'On' else 'On')):
            raise InstallationPrecondition('Requested power action is not supported in the observed state; no restart sent')
        method, tag, body = 'POST', etag(system), {'ResetType': args['resetType']}
    evidence.append(tag)
    # Approval is invalidated if the observed ETags/payload/route change. Do not
    # expose raw ETags (or any arbitrary BMC strings) in the approval UI.
    digest = hashlib.sha256(json.dumps([method, path, body, evidence], sort_keys=True).encode()).hexdigest()
    return method, path, body, tag, {'stateHash': digest, 'review': review}


@contextlib.contextmanager
def target_lock(root, endpoint):
    directory = root/'connection-installation-locks'
    directory.mkdir(mode=0o700, exist_ok=True)
    credentials._private(directory, directory=True)
    path = directory/(hashlib.sha256(endpoint.encode()).hexdigest()+'.lock')
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        # Same host target across owners; no two controlled changes in parallel.
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        os.close(fd)


def write_json(origin, method, path, headers, body, *, ignore_certificate_errors=False):
    """One direct request, no proxy/redirect/retry/raw response or async claim."""
    context = ssl.create_default_context()
    if ignore_certificate_errors is True:
        context.check_hostname = False; context.verify_mode = ssl.CERT_NONE
    c = http.client.HTTPSConnection(urlsplit(origin).hostname, 443, timeout=10, context=context)
    try:
        c.request(method, path, body=json.dumps(body).encode(), headers={**headers,
                  'Content-Type': 'application/json', 'Accept': 'application/json'})
        response = c.getresponse()
        # 202 is only queued, not completion. Never follow task-monitor URLs or
        # assume a rejected/failed response proves that no side effect happened.
        return response.status in (200, 204)
    finally:
        c.close()


def dispatch(manager, request, owner, claim, row, values, transport, authorized,
             ignore_certificate_errors=False, write_transport=None):
    if row.get('httpTransport') != 'direct' or os.environ.get('PRIME_CONNECTION_BMC_WRITES_ENABLED') != '1':
        raise PermissionError('BMC installation runtime is not enabled for direct transport')
    operation, args = request['operation'], request.get('arguments', {})
    approvals = Approvals(manager.root)
    if operation == 'redfish.receipt':
        return approvals.receipt(owner, claim, request['connection'], args)
    if operation == 'redfish.installation':
        return connections.perform(row, values, operation, args, transport)
    validate(operation, args, row['endpoint'])
    previous = approvals.previous(owner, claim, request['connection'], row, operation, args)
    if previous:
        return previous
    target = connections.endpoint(values.get('endpoint'))
    if target != row['endpoint'] or not values.get('username') or not values.get('password') or ':' in values['username']:
        raise ValueError('Saved target does not match')
    header = 'Basic '+base64.b64encode((values['username']+':'+values['password']).encode()).decode()
    get = lambda path: transport(target, path, {'Authorization': header})
    with target_lock(manager.root, target):
        method, path, body, tag, preconditions = plan(operation, args, row, get, approvals, owner, claim, request['connection'])
        pending = approvals.require(owner, claim, request['connection'], row, operation, args, preconditions=preconditions)
        if pending:
            return pending
        acknowledged = False
        try:
            authorized()  # consume-before-send already persisted; revocation fails closed
            send = write_transport or write_json
            acknowledged = send(target, method, path, {'Authorization': header, 'If-Match': tag}, body,
                                ignore_certificate_errors=ignore_certificate_errors) is True
        except Exception:
            pass  # unknown is durable, and upstream/credential text is withheld
        return approvals.finish(owner, claim, request['connection'], args, acknowledged)
