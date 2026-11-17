import pathlib, re

d = pathlib.Path(__file__).parent
root = d.parent
L = (root / "area-sessions.html").read_text().split("\n")
i_head = next(i for i, l in enumerate(L) if l.strip() == "</head>")
head = "\n".join(L[:i_head]).replace("<title>Sessions</title>", "<title>Sessions, round two</title>")
H = (root / "area-home.html").read_text().split("\n")
i_tail = max(i for i, l in enumerate(H) if l.strip() == "<script>")
tail = "\n".join(H[i_tail:])
parts = [p.read_text() for p in sorted(d.glob("part-*.html"))]
styles = "".join(m for p in parts for m in re.findall(r"<style>.*?</style>", p, re.S)[:1])
bodies = [re.sub(r"<style>.*?</style>", "", p, count=1, flags=re.S) for p in parts]
body = (
    '<body data-title="Sessions, round two" data-desc="A second, deeper round for paper and live '
    "sessions: the list, a running session, a rebalance, a rejected order, a frozen sleeve and how "
    "it gets resolved, deploying to paper, moving from paper to live with real money, stopping a "
    'session and the phone. The annotated timeline from Home carries through most of them.">'
)
out = head + "\n" + styles + "\n</head>\n" + body + "\n" + "\n".join(bodies) + "\n" + tail + "\n"
(root / "area-sessions-2.html").write_text(out)
print("ok", len(parts), "parts", len(out), "bytes")
