"use strict";
const element=id=>document.getElementById(id);
let selected="",paused=false,lastFrame=0;
function clearScreen(message){element("frame").hidden=true;element("frame").removeAttribute("src");element("terminal").hidden=true;element("terminal").textContent="";element("empty").hidden=false;element("empty").textContent=message;lastFrame=0;}
async function getJSON(url){const response=await fetch(url,{cache:"no-store",credentials:"same-origin"});if(response.redirected||response.status===401||response.status===403)throw new Error("Sign in to Prime WebUI to view your consoles.");if(!response.ok)throw new Error(response.status===404?"This console has closed or expired.":"Console feed temporarily unavailable.");if(!(response.headers.get("Content-Type")||"").includes("application/json"))throw new Error("Sign in to Prime WebUI to view your consoles.");return response.json();}
async function refresh(){const started=Date.now();try{if(paused||document.hidden){element("status").textContent=paused?"View paused · the agent is still working":"View suspended while this window is hidden";return;}
const data=await getJSON("/api/consoles?watch=1"),sessions=data.sessions||[],picker=element("source");
if(!sessions.some(s=>s.id===selected))selected=(sessions.find(s=>s.state!=="closed"&&!s.stale)||sessions[0])?.id||"";
picker.replaceChildren();for(const s of sessions){const option=document.createElement("option");option.value=s.id;option.textContent=`${s.title||s.kind||"Console"}${s.state==="closed"?" · closed":s.stale?" · stale":""}`;picker.append(option);}picker.value=selected;
if(!selected){const option=document.createElement("option");option.textContent="Waiting for a console";picker.append(option);clearScreen("No active browser or console yet. Start a supported skill; it will appear here automatically. Existing tasks may need the updated runtime on their next start.");element("status").textContent="Waiting for agent console";return;}
const row=(await getJSON(`/api/consoles/frame?id=${encodeURIComponent(selected)}`)).session;
if(!row||row.state==="closed"){clearScreen("This console has closed. Choose another source or wait for the agent to open one.");element("status").textContent="Console closed";return;}
if(row.image){element("frame").src=`data:image/jpeg;base64,${row.image}`;element("frame").hidden=false;element("terminal").hidden=true;element("empty").hidden=true;}
else if(row.kind==="serial"&&row.text){element("terminal").textContent=row.text;element("terminal").hidden=false;element("frame").hidden=true;element("empty").hidden=true;}
else clearScreen("Waiting for the first frame. The agent may be navigating or using the console.");
lastFrame=Number(row.frameAt)||0;
element("status").textContent=row.stale?"No recent update · the task may have stopped or be busy":row.kind==="serial"?"Serial console · agent’s last read":row.state==="busy"?"Agent operation in progress · waiting for a fresh frame":"Connected · read-only live view";
}catch(error){clearScreen(error.message);element("status").textContent=error.message;}finally{element("freshness").textContent=lastFrame?`Last frame ${Math.max(0,Math.floor(Date.now()/1000-lastFrame))}s ago`:"No frame yet";setTimeout(refresh,Math.max(100,1000-(Date.now()-started)));}}
element("source").onchange=()=>{selected=element("source").value;clearScreen("Switching console…");};
element("pause").onclick=()=>{paused=!paused;element("pause").textContent=paused?"Resume view":"Pause view";};
element("fit").onclick=()=>{const actual=element("screen").classList.toggle("actual");element("fit").textContent=actual?"Fit to window":"Actual size";};
refresh();
