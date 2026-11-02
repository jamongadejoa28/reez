// GPL-3.0-only. Windows Studio bridge to the local C/Clang conversion backend.
"use strict";
const fs = require("fs");
const os = require("os");
const path = require("path");
const cp = require("child_process");
function execute(file,args,options={}) {
    return new Promise((resolve,reject)=>cp.execFile(file,args,{windowsHide:true,timeout:600000,maxBuffer:16*1024*1024,...options},(error,stdout,stderr)=>{
        if(error)reject(new Error(stderr.trim() || stdout.trim() || error.message));else resolve(stdout);
    }));
}
async function run(request) {
    const work=fs.mkdtempSync(path.join(os.tmpdir(),"reez-c-build-"));
    try {
        const file=path.join(work,"request.json");fs.writeFileSync(file,JSON.stringify(request));
        if (process.platform === "win32") {
            const distro=request.settings?.wslDistro;
            const prefix=distro?["-d",distro,"--exec"]:["--exec"];
            const backend=(await execute("wsl.exe",[...prefix,"wslpath","-u",path.join(__dirname,"backend","convert.py")])).trim();
            const input=(await execute("wsl.exe",[...prefix,"wslpath","-u",file])).trim();
            return await execute("wsl.exe",[...prefix,"python3",backend,"--request",input]);
        }
        return await execute("python3",[path.join(__dirname,"backend","convert.py"),"--request",file]);
    } finally {fs.rmSync(work,{recursive:true,force:true});}
}
if(require.main===module){
    const args=process.argv.slice(2);const index=args.indexOf("--request");
    const request=index>=0?JSON.parse(fs.readFileSync(args[index+1],"utf8")):{operation:"check",settings:{}};
    run(request).then(text=>process.stdout.write(text)).catch(error=>{console.error(JSON.stringify({path:"c-output-backend",message:error.message}));process.exitCode=1;});
}
exports.run=run;
