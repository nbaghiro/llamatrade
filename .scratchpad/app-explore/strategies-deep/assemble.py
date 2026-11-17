import pathlib,re
d=pathlib.Path(__file__).parent; root=d.parent
S=(root/'area-strategies.html').read_text().split('\n')
H=(root/'area-home.html').read_text().split('\n')
head='\n'.join(S[:336]).replace('<title>Strategies</title>','<title>Strategies, round two</title>')
tail='\n'.join(H[1667:])  # top-bar script + kit.js + </body></html>
files=['part-list.html','part-templates.html','part-detail-a.html','part-detail-b.html']
parts=[(d/f).read_text() for f in files if (d/f).exists()]
styles='\n'.join(m for p in parts for m in re.findall(r'<style>.*?</style>',p,re.S)[:1])
bodies=[re.sub(r'<style>.*?</style>','',p,count=1,flags=re.S) for p in parts]
body='<body data-title="Strategies, round two" data-desc="A deeper second batch for Strategies only: the list and its empty state, the templates gallery and preview, and each part of a strategy\'s own page.">'
(root/'area-strategies-2.html').write_text(head+'\n'+styles+'\n</head>\n'+body+'\n'+'\n'.join(bodies)+'\n'+tail)
print('ok',len(parts))
