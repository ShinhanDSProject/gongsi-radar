// 리뷰 화면 빌드: src/*.jsx → 단일 HTML 두 벌
//   dist/index.html     완전한 HTML 문서(로컬 서버·python -m radar demo가 리포트를 심어 씀)
//   dist/artifact.html  claude.ai Artifact로 게시하는 본문 조각(doctype/html/head/body 없이)
// React 18.3.1 UMD는 cdnjs에서 불러오고, 앱 코드는 전역 React/ReactDOM을 쓴다.
// 실행: cd web && npm install && node build.mjs   (esbuild만 필요)
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
let esbuild;
try {
  esbuild = await import('esbuild');
} catch {
  esbuild = await import(process.env.ESBUILD_PATH || '/opt/npm-tools/node_modules/esbuild/lib/main.js');
}

const report = process.argv[2] ? readFileSync(process.argv[2], 'utf-8') : null; // 선택: 리포트 JSON을 심어 빌드

const out = await esbuild.build({
  entryPoints: [join(here, 'src/main.jsx')],
  bundle: true,
  write: false,
  format: 'iife',
  target: ['es2019'],
  jsx: 'transform',
  jsxFactory: 'React.createElement',
  jsxFragment: 'React.Fragment',
  minify: true,
  legalComments: 'none',
});
const js = out.outputFiles[0].text.replace(/<\/script/gi, '<\\/script');
const css = readFileSync(join(here, 'src/styles.css'), 'utf-8');
const tpl = readFileSync(join(here, 'src/index.template.html'), 'utf-8');
const [head, body] = tpl.replace('<!--HEAD-->', '').split('<!--BODY-->');
const fill = (s) => s.replace('/*__CSS__*/', () => css).replace('/*__JS__*/', () => js);
const embed = (s) => report
  ? s.replace('<script id="radar-report" type="application/json">null</script>',
    () => `<script id="radar-report" type="application/json">${report.replace(/<\//g, '<\\/')}</script>`)
  : s;

mkdirSync(join(here, 'dist'), { recursive: true });
const full = `<!doctype html>\n<html lang="ko">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n${fill(head).trim()}\n</head>\n<body>\n${fill(body).trim()}\n</body>\n</html>\n`;
writeFileSync(join(here, 'dist/index.html'), embed(full));
writeFileSync(join(here, 'dist/artifact.html'), embed(`${fill(head).trim()}\n${fill(body).trim()}\n`));
console.log(`built dist/index.html, dist/artifact.html (js ${(js.length / 1024).toFixed(1)}KB${report ? ', 리포트 포함' : ''})`);
