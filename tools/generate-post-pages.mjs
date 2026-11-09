// 글 개별 정적 페이지 생성기
// site/index.html의 POSTS 배열을 읽어 글마다 site/post/<id>.html을 만든다.
// 검색엔진이 글 단위로 색인할 수 있게 본문·메타·canonical·OG·JSON-LD를 정적으로 박는다.
// 사용법: node tools/generate-post-pages.mjs  (글을 추가/수정한 뒤 실행, 결과물을 함께 커밋)
// 사이트맵(site/sitemap.xml)도 글 URL을 포함해 함께 재생성한다.
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = dirname(dirname(fileURLToPath(import.meta.url)));
const SITE = ROOT + '/site';
const BASE = 'https://hongzi.us';

const indexHtml = readFileSync(SITE + '/index.html', 'utf8');

// ── index.html에서 공유 자산 추출 ──
const style = indexHtml.match(/<style>([\s\S]*?)<\/style>/)[1];
const gaBlock = indexHtml.match(/<!-- Google tag \(gtag\.js\) -->[\s\S]*?adsbygoogle\.js\?client=ca-pub-4973471145275269"[^>]*><\/script>/)[0];
const fontLinks = [
  '<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css" />',
  '<link rel="preconnect" href="https://fonts.googleapis.com" />',
  '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />',
  '<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+KR:wght@400;500;600&display=swap" rel="stylesheet" />',
].join('\n    ');

// ── POSTS 배열 파싱 ──
const postsMatch = indexHtml.match(/var POSTS = (\[[\s\S]*?\n\s*\]);/);
if (!postsMatch) throw new Error('POSTS array not found');
const POSTS = new Function('return ' + postsMatch[1])();
const ids = new Set(POSTS.map((p) => p.id));

const esc = (s) => String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const isoDate = (meta0) => {
  const m = String(meta0).match(/(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})/);
  return m ? `${m[1]}-${m[2].padStart(2, '0')}-${m[3].padStart(2, '0')}` : null;
};
// 글 내부 링크를 정적 페이지 주소로 변환 (대상 글이 POSTS에 없으면 기존 해시 경로 유지)
const mapUrl = (url) => {
  const hash = String(url).match(/^#\/post\/([\w-]+)$/);
  if (hash) return ids.has(hash[1]) ? `/post/${hash[1]}.html` : `/${url}`;
  if (/^[\w-]+\.html$/.test(url)) return '/' + url;
  return url;
};

function renderPost(post, idx) {
  const url = `${BASE}/post/${post.id}.html`;
  const date = isoDate(post.meta && post.meta[0]);
  const metaRow = (post.meta || []).map(esc).join('<i>·</i>');
  const sections = (post.sections || []).map((sec) => {
    let out = `        <section>\n          <h3>${esc(sec.h)}</h3>\n`;
    (sec.paras || []).forEach((p) => { out += `          <p${sec.small ? ' class="small"' : ''}>${esc(p)}</p>\n`; });
    if (sec.items && sec.items.length) {
      out += '          <ul>\n' + sec.items.map((it) => `            <li>${esc(it)}</li>`).join('\n') + '\n          </ul>\n';
    }
    return out + '        </section>';
  }).join('\n');
  let linksSec = '';
  if (post.links && post.links.length) {
    const lis = post.links.map((lk) => {
      const href = mapUrl(lk.url);
      const ext = /^https?:\/\//.test(href) ? ' target="_blank" rel="noopener"' : '';
      return `            <li><a href="${esc(href)}"${ext}>${esc(lk.label)}</a> <span class="d">${esc(lk.desc)}</span></li>`;
    }).join('\n');
    linksSec = `\n        <section>\n          <h3>출처 · 바로가기</h3>\n          <ul class="linklist">\n${lis}\n          </ul>\n        </section>`;
  }
  const watch = post.watch ? `\n        <div class="watchbox"><strong>영상 보기 — </strong>영상 재생은 유튜브에서 합니다. <a href="https://www.youtube.com/@%EC%A7%80%EC%A1%B0%EA%B0%81" target="_blank" rel="noopener">유튜브 채널 ‘지혜로운 조각들’ (@지조각) →</a></div>` : '';
  const prev = idx > 0 ? POSTS[idx - 1] : null;
  const next = idx < POSTS.length - 1 ? POSTS[idx + 1] : null;
  const nav = `\n      <nav class="detail-nav" aria-label="다른 글">${prev ? `\n        <a href="/post/${prev.id}.html"><span class="dir">이전 글</span>${esc(prev.title)}</a>` : ''}${next ? `\n        <a class="next" href="/post/${next.id}.html"><span class="dir">다음 글</span>${esc(next.title)}</a>` : ''}\n      </nav>`;
  const jsonLd = JSON.stringify({
    '@context': 'https://schema.org', '@type': 'BlogPosting',
    headline: post.title, description: post.summary,
    image: [`${BASE}/${post.img}`], datePublished: date,
    author: { '@type': 'Person', name: 'HongSungIn', url: BASE + '/' },
    mainEntityOfPage: url,
  });
  return `<!doctype html>
<html lang="ko">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
    <meta name="color-scheme" content="light dark" />
    <link rel="icon" href="data:," />
    <title>${esc(post.title)} — HongSungIn</title>
    <meta name="description" content="${esc(post.summary)}" />
    <link rel="canonical" href="${url}" />
    <meta property="og:type" content="article" />
    <meta property="og:site_name" content="HongSungIn" />
    <meta property="og:title" content="${esc(post.title)}" />
    <meta property="og:description" content="${esc(post.summary)}" />
    <meta property="og:url" content="${url}" />
    <meta property="og:image" content="${BASE}/${post.img}" />
    ${date ? `<meta property="article:published_time" content="${date}" />` : ''}
    <meta name="twitter:card" content="summary_large_image" />
    <meta name="google-site-verification" content="TE_a5yGhqMM-wjQRCvo9Cc7LzAlbduAlwCKos1kQ6Qw" />
    ${fontLinks}
    <style>${style}
      .detail-head h1 { margin: 10px 0 12px; font-size: 30px; font-weight: 600; line-height: 1.4; letter-spacing: -0.02em; }
      .postfoot { border-top: 1px solid var(--line-soft); margin-top: 44px; padding: 22px 0 36px; font-size: 13.5px; color: var(--muted); }
      .postfoot a { color: var(--ink-soft); text-decoration: none; }
      .postfoot a:hover { text-decoration: underline; text-underline-offset: 4px; }
    </style>
    <script type="application/ld+json">${jsonLd}</script>
  ${gaBlock}
  </head>
  <body>
    <div class="wrap">
      <article class="detail">
        <a class="backlink" href="/#posts">← 글 목록으로</a>
        <div class="detail-head">
          <span class="tag">${esc(post.tag)}</span>
          <h1 class="serif">${esc(post.title)}</h1>
          <div class="meta">${metaRow}</div>
        </div>
        <div class="detail-hero"><img src="/${esc(post.img)}" alt="${esc(post.alt)}" /></div>
        <div class="detail-body">
${sections}${linksSec}${watch}
        </div>${nav}
      </article>
      <footer class="postfoot">© 2026 HongSungIn · <a href="/">hongzi.us 홈으로</a></footer>
    </div>
  </body>
</html>
`;
}

mkdirSync(SITE + '/post', { recursive: true });
POSTS.forEach((post, i) => {
  writeFileSync(`${SITE}/post/${post.id}.html`, renderPost(post, i));
});
console.log(`generated ${POSTS.length} post pages`);

// ── 사이트맵 재생성 ──
const today = new Date().toISOString().slice(0, 10);
const fixed = [
  { loc: BASE + '/', lastmod: today, changefreq: 'weekly', priority: '1.0' },
  { loc: BASE + '/ai-trading.html', lastmod: '2026-10-27', changefreq: 'monthly', priority: '0.8' },
  { loc: BASE + '/kakao.html', lastmod: '2026-10-24', changefreq: 'monthly', priority: '0.8' },
  { loc: BASE + '/seedance.html', lastmod: '2026-10-21', changefreq: 'monthly', priority: '0.7' },
  { loc: BASE + '/fpv.html', lastmod: '2026-10-22', changefreq: 'monthly', priority: '0.7' },
];
const postUrls = POSTS.map((p) => ({
  loc: `${BASE}/post/${p.id}.html`, lastmod: isoDate(p.meta && p.meta[0]) || today,
  changefreq: 'monthly', priority: '0.7',
}));
const urls = [...fixed, ...postUrls];
const xml = `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n` +
  urls.map((u) => `  <url>\n    <loc>${u.loc}</loc>\n    <lastmod>${u.lastmod}</lastmod>\n    <changefreq>${u.changefreq}</changefreq>\n    <priority>${u.priority}</priority>\n  </url>`).join('\n') +
  `\n</urlset>\n`;
writeFileSync(SITE + '/sitemap.xml', xml);
console.log(`sitemap: ${urls.length} urls`);
