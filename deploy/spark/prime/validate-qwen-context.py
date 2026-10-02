#!/usr/bin/env python3
"""Synthetic local Qwen tests. Run on Spark with no user task using the slot.

--long runs a near-limit recall test; prints metrics, never private reasoning.
Fails below the 15% host available-memory reserve.
"""
import json
import sys
import threading
import time
import urllib.request

URL = 'http://127.0.0.1:30001'


def post(path, payload):
    request = urllib.request.Request(URL+path, json.dumps(payload).encode(), {'Content-Type':'application/json'})
    with urllib.request.urlopen(request, timeout=1800) as response:
        return json.load(response)


def memory():
    with open('/proc/meminfo') as stream:
        values={line.split(':')[0]:int(line.split()[1])*1024 for line in stream}
    return values['MemAvailable'], values['MemTotal']


def main():
    initial,total=memory(); samples=[initial]; finished=threading.Event()
    def sample():
        while not finished.wait(1): samples.append(memory()[0])
    threading.Thread(target=sample,daemon=True).start()
    try:
        for effort in ('low','xhigh'):
            start=time.monotonic()
            result=post('/v1/chat/completions',{'model':'qwen3.8-flash-next','messages':[{'role':'user','content':'Calculate 37 * 19. Reply with only the integer.'}], 'reasoning_effort':effort,'max_tokens':512,'temperature':0})
            content=result['choices'][0]['message'].get('content','').strip()
            assert content=='703', (effort,content)
            print(json.dumps({'effort':effort,'seconds':round(time.monotonic()-start,2),'usage':result.get('usage'),'timings':result.get('timings'),'answer':content}),flush=True)
        if '--long' in sys.argv:
            # Exercise the real chat endpoint, not unframed raw completion: an
            # instruction model may immediately emit EOS for a raw document.
            # Count the rendered template, leaving room for Prime's 8K reserve.
            filler='This is an ordinary archive entry without any access marker.\n'
            unit=len(post('/tokenize',{'content':filler,'add_special':False})['tokens'])
            repetitions=(250000-128)//unit
            document='Document. The unique access marker is OAK-7391-LIME. Remember it.\n'+filler*repetitions
            document+='\nQuestion: What was the unique access marker at the beginning? Reply with only that marker.'
            payload={'model':'qwen3.8-flash-next','messages':[{'role':'user','content':document}],
                     'reasoning_effort':'low','max_tokens':512,'temperature':0}
            rendered=post('/apply-template',payload)['prompt']
            count=len(post('/tokenize',{'content':rendered,'add_special':False,'parse_special':True})['tokens'])
            assert 240000 <= count <= 253952, f'Unexpected chat input size: {count}'
            print(json.dumps({'long_prompt_tokens':count,'status':'prefilling_chat'}),flush=True)
            start=time.monotonic()
            result=post('/v1/chat/completions',payload)
            content=result['choices'][0]['message'].get('content','').strip()
            print(json.dumps({'long_seconds':round(time.monotonic()-start,2),'answer':content,'timings':result.get('timings'),'usage':result.get('usage')}),flush=True)
            assert 'OAK-7391-LIME' in content, 'Long-range recall failed'
            assert result['usage']['prompt_tokens'] >= 240000, 'Context was truncated'
        samples.append(memory()[0])
        minimum=min(samples)
        print(json.dumps({'available_GiB':round(samples[-1]/2**30,2),'minimum_available_GiB':round(minimum/2**30,2),'minimum_available_percent':round(minimum/total*100,2)}),flush=True)
        assert minimum/total >= .15, 'Available RAM fell below 15% reserve'
    finally:
        finished.set()
        print(json.dumps({'sampled_minimum_available_GiB':round(min(samples)/2**30,2)}),flush=True)


if __name__=='__main__':main()
