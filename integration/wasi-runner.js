// GPL-3.0-only. Execute the bundled Rust generator in EEZ Studio's Node runtime.
"use strict";
const fs = require("fs");
const path = require("path");
const os = require("os");

async function main(args) {
    const value = key => { const i = args.indexOf(key); return i < 0 ? null : args[i + 1]; };
    const check = args.includes("--check");
    const version = args.includes("--version");
    const module = await WebAssembly.compile(fs.readFileSync(path.join(__dirname,"bin","reez.wasm")));
    const work = fs.mkdtempSync(path.join(os.tmpdir(), "reez-wasi-"));
    let output = null;
    try {
        const preopens = { "/work": work };
        fs.mkdirSync(path.join(work,"tmp"));
        function execute(arguments_, capture) {
            const { WASI } = require("wasi");
            const fd = fs.openSync(path.join(work,capture),"w");
            try {
                const wasi = new WASI({version:"preview1",args:arguments_,env:{TMPDIR:"/work/tmp",PWD:"/work"},preopens,returnOnExit:true,stdout:fd});
                const instance = new WebAssembly.Instance(module,{wasi_snapshot_preview1:wasi.wasiImport});
                return wasi.start(instance);
            } finally { fs.closeSync(fd); }
        }
        let wasiArgs = ["reez", ...args];
        if (!version) {
            const input = value("--project");
            if (!input) throw new Error("--project is required");
            const sourceFile = path.resolve(input);
            const project = JSON.parse(fs.readFileSync(sourceFile,"utf8"));
            output = path.resolve(value("--out") || path.join(path.dirname(sourceFile),"rust-src"));
            const outputParent = path.dirname(output);
            const originalCOutput = path.resolve(path.dirname(sourceFile), (project.settings?.build?.destinationFolder || ".").replace(/\\/g,path.sep));
            function resolved(p) {
                if (fs.existsSync(p)) return fs.realpathSync(p);
                const parent = path.dirname(p);
                return parent === p ? p : path.join(resolved(parent),path.basename(p));
            }
            const nested = (a,b) => { const relative = path.relative(a,b);return relative === "" || (!relative.startsWith(".."+path.sep) && relative!==".." && !path.isAbsolute(relative)); };
            const outResolved=resolved(output), baseResolved=resolved(path.dirname(sourceFile)), cResolved=resolved(originalCOutput);
            if (nested(outResolved,baseResolved) || nested(outResolved,cResolved) || nested(cResolved,outResolved)) throw new Error("Rust output must be separate from the project and C output directories");

            const shadowCOutput = path.join(work,"c-output"); fs.mkdirSync(shadowCOutput);
            preopens["/c-output"] = fs.existsSync(originalCOutput) ? originalCOutput : shadowCOutput;
            if (project.settings?.build) project.settings.build.destinationFolder = "/c-output";
            fs.writeFileSync(path.join(work,"input.eez-project"),JSON.stringify(project));
            // Validate in Rust before invoking the converter's CLI argument parser.
            const validation = execute(["reez","--project","/work/input.eez-project","--check"],"validation.log");
            if (validation !== 0) return validation;
            if (!check) {
                fs.mkdirSync(outputParent,{recursive:true});
                preopens["/output"] = outputParent;
                const fonts = path.join(work,"fonts"); fs.mkdirSync(fonts);
                const converter = require("./node_modules/lv_font_conv/lib/cli");
                for (const [index,font] of (project.fonts || []).entries()) {
                    if (!Number.isInteger(font.source?.size) || font.source.size <= 0 || ![1,2,3,4,8].includes(font.bpp) || !(font.lvglRanges || font.lvglSymbols)) {
                        throw new Error(`fonts[${index}]: invalid size, bpp, or glyph selection`);
                    }
                    const ttf = path.join(work,`${index}.ttf`);
                    if (font.embeddedFontFile) {
                        const encoded = font.embeddedFontFile.includes(",") ? font.embeddedFontFile.slice(font.embeddedFontFile.indexOf(",")+1) : font.embeddedFontFile;
                        fs.writeFileSync(ttf,Buffer.from(encoded,"base64"));
                    } else fs.copyFileSync(path.resolve(path.dirname(sourceFile),(font.source?.filePath || "").replace(/\\/g,"/")),ttf);
                    const parameters = ["--font",ttf,"--size",String(font.source.size),"--bpp",String(font.bpp),"--format","bin","--no-compress","--output",path.join(fonts,`${index}.bin`)];
                    if (font.lvglRanges) {
                        converter._range(font.lvglRanges);
                        parameters.push("--range",font.lvglRanges);
                    }
                    if (font.lvglSymbols) parameters.push("--symbols",font.lvglSymbols);
                    await converter.run(parameters);
                }
            }
            wasiArgs = ["reez","--project","/work/input.eez-project",...(check?["--check"]:["--out",`/output/${path.basename(output)}`,"--prepared-fonts","/work/fonts"])];
        }
        const code = execute(wasiArgs,"output.log");
        const text = fs.readFileSync(path.join(work,"output.log"),"utf8");
        for (const line of text.trim().split("\n").filter(Boolean)) {
            if (line.startsWith("{")) {
                const summary = JSON.parse(line);if (output) summary.output = output;
                console.log(JSON.stringify(summary));
            } else console.log(line);
        }
        return code;
    } finally { fs.rmSync(work,{recursive:true,force:true}); }
}
if (require.main === module) main(process.argv.slice(2)).then(code=>{process.exitCode=code;}).catch(error=>{
    console.error(JSON.stringify({path:"runtime",message:error.message}));process.exitCode=1;
});
exports.main=main;
