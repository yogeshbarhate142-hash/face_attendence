const $=id=>document.getElementById(id);let enrollStream=null,checkStream=null;
async function postJSON(url,data){const r=await fetch(url,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(data)});const d=await r.json();if(!r.ok)throw Error(d.error||"Request failed");return d}
async function startCam(videoId, facing="user"){const v=$(videoId);const s=await navigator.mediaDevices.getUserMedia({video:{facingMode:{ideal:facing}},audio:false});v.srcObject=s;await v.play();return v}
function snap(v){if(!v||!v.videoWidth)throw Error("Enable camera and wait until video appears.");const c=document.createElement("canvas");c.width=v.videoWidth;c.height=v.videoHeight;c.getContext("2d").drawImage(v,0,0);return new Promise(resolve=>c.toBlob(resolve,"image/jpeg",.9))}
function showDashboard(org){$("auth").hidden=true;$("dashboard").hidden=false;$("orgTitle").textContent=org.name;$("orgCode").textContent=org.code;$("orgBadge").textContent=org.name;$("checkOrg").value=org.code;loadReport()}
async function refreshSession(){try{const r=await fetch("/api/admin/me");if(r.ok){const d=await r.json();showDashboard(d.organization)}}catch(e){}}
document.querySelectorAll("[data-tab]").forEach(b=>b.onclick=()=>{document.querySelectorAll("[data-tab]").forEach(x=>x.classList.toggle("active",x===b));$("signupPane").hidden=b.dataset.tab!=="signup";$("loginPane").hidden=b.dataset.tab!=="login";$("authMsg").textContent=""});
$("signup").onclick=async()=>{try{const d=await postJSON("/api/org/signup",{org_name:$("orgName").value,email:$("newEmail").value,password:$("newPassword").value});$("authMsg").textContent="Organization created. Save the organization code shown in your dashboard.";showDashboard({name:$("orgName").value,code:d.organization_code})}catch(e){$("authMsg").textContent=e.message}};
$("login").onclick=async()=>{try{const d=await postJSON("/api/admin/login",{email:$("loginEmail").value,password:$("loginPassword").value});await refreshSession()}catch(e){$("authMsg").textContent=e.message}};
$("logout").onclick=async()=>{await postJSON("/api/admin/logout",{});location.reload()};
$("enrollCamera").onclick=async()=>{try{enrollStream=await startCam("enrollVideo");$("enrollMsg").textContent="Camera ready."}catch(e){$("enrollMsg").textContent=e.message}};
$("checkCamera").onclick=async()=>{try{checkStream=await startCam("checkVideo");$("checkMsg").textContent="Camera ready."}catch(e){$("checkMsg").textContent=e.message}};
$("enroll").onclick=async()=>{try{if(!enrollStream)throw Error("Enable camera first.");const f=new FormData();f.append("full_name",$("memberName").value);f.append("member_code",$("memberCode").value);f.append("face",await snap($("enrollVideo")),"face.jpg");const r=await fetch("/api/admin/members",{method:"POST",body:f});const d=await r.json();if(!r.ok)throw Error(d.error);$("enrollMsg").textContent=d.message+" Member ID: "+d.member_id;loadReport()}catch(e){$("enrollMsg").textContent=e.message}};
$("checkin").onclick=async()=>{try{if(!checkStream)throw Error("Enable camera first.");const f=new FormData();f.append("org_code",$("checkOrg").value);f.append("member_code",$("checkMember").value);f.append("face",await snap($("checkVideo")),"live.jpg");const r=await fetch("/api/attendance",{method:"POST",body:f});const d=await r.json();if(!r.ok)throw Error(d.error);$("checkMsg").textContent=d.message+" · "+d.member+" · "+new Date(d.marked_at).toLocaleString();loadReport()}catch(e){$("checkMsg").textContent=e.message}};
async function loadReport(){try{const r=await fetch("/api/admin/report");if(!r.ok)return;const d=await r.json();$("memberCount").textContent=d.member_count+" enrolled members";$("records").innerHTML="";if(!d.records.length){$("records").textContent="No check-ins yet.";return}d.records.forEach(x=>{const row=document.createElement("div");row.className="record";const a=document.createElement("b");a.textContent=x.full_name+" · "+x.member_code;const b=document.createElement("span");b.textContent=(x.event_type==="CHECK_IN"?"IN · ":"OUT · ")+new Date(x.marked_at).toLocaleString("en-IN",{timeZone:"Asia/Kolkata"});row.append(a,b);$("records").append(row)})}catch(e){}}
$("refresh").onclick=loadReport;refreshSession();


// Shared entrance kiosk: one camera, no member code prompt.
let kioskStream=null, kioskBusy=false;
let kioskFacing="environment";
let kioskTimer=null;
let kioskLastResultAt=0;
let kioskLastResultKey="";
let kioskAutoEnabled=false;

function stopAutoKiosk(message="Automatic scanning stopped.") {
  kioskAutoEnabled=false;
  if(kioskTimer){clearInterval(kioskTimer);kioskTimer=null;}
  $("kioskScan").textContent="Start automatic scanning";
  $("kioskMsg").textContent=message;
}
$("cameraFlip").onclick=async()=>{
  try{
    if(kioskStream) kioskStream.getTracks().forEach(t=>t.stop());
    kioskFacing=kioskFacing==="environment"?"user":"environment";
    kioskStream=await startCam("kioskVideo",kioskFacing);
    $("cameraFlip").textContent=kioskFacing==="environment"?"Use front camera":"Use rear camera";
    $("kioskMsg").textContent="Camera switched. Keep the phone stable and position one person in the marked check-in area.";
  }catch(e){$("kioskMsg").textContent=e.message}
};
$("kioskCamera").onclick=async()=>{
  try{
    if(kioskStream) kioskStream.getTracks().forEach(t=>t.stop());
    kioskStream=await startCam("kioskVideo",kioskFacing);
    $("kioskMsg").textContent="Camera ready. Read the privacy notice and start automatic scanning when the kiosk area is ready.";
  }catch(e){$("kioskMsg").textContent=e.message}
};

async function kioskScanOnce() {
  if(kioskBusy || !kioskAutoEnabled) return;
  kioskBusy=true;
  const msg=$("kioskMsg");
  try{
    const code=$("kioskOrg").value.trim();
    if(!code) throw Error("Enter the organization code.");
    const f=new FormData();
    f.append("org_code",code);
    f.append("face",await snap($("kioskVideo")),"kiosk.jpg");
    const r=await fetch("/api/kiosk/identify",{method:"POST",body:f});
    const d=await r.json();
    if(!r.ok) throw Error(d.error||"Kiosk scan failed.");
    if(d.status==="success"){
      const time=new Date(d.marked_at).toLocaleTimeString("en-IN",{timeZone:"Asia/Kolkata"});
      const key=d.member+"|"+d.event_type+"|"+d.marked_at.slice(0,10);
      // Avoid repeating the same success message while the same person remains in view.
      if(key!==kioskLastResultKey || Date.now()-kioskLastResultAt>8000){
        msg.textContent="✓ "+d.event_label+": "+d.member+" · "+time+" IST";
        kioskLastResultKey=key;kioskLastResultAt=Date.now();
        loadReport();
      }
      // Give the person time to leave the frame before another scan.
      stopAutoKiosk("✓ "+d.event_label+" recorded for "+d.member+". Ready for the next person.");
      return;
    } else if(d.status==="already_completed" || d.status==="already_marked"){
      msg.textContent=d.message+(d.member?" · "+d.member:"");
      // Avoid repeatedly querying a face that remains in front of the camera.
      stopAutoKiosk(msg.textContent);
      return;
    } else {
      msg.textContent=d.message||"No match. Keep one face centered and try again.";
    }
  }catch(e){
    msg.textContent=e.message;
    if(e.message.includes("Enter the organization code")) stopAutoKiosk(e.message);
  }finally{kioskBusy=false;}
}
$("kioskScan").onclick=async()=>{
  if(kioskAutoEnabled){stopAutoKiosk();return;}
  if(!kioskStream){$("kioskMsg").textContent="Enable the entrance camera first.";return;}
  if(!$("kioskOrg").value.trim()){$("kioskMsg").textContent="Enter the organization code first.";return;}
  kioskAutoEnabled=true;
  $("kioskScan").textContent="Stop automatic scanning";
  $("kioskMsg").textContent="Automatic scanning is active. Only one person should stand in the marked camera area at a time.";
  await kioskScanOnce();
  if(kioskAutoEnabled) kioskTimer=setInterval(kioskScanOnce,3000);
};
