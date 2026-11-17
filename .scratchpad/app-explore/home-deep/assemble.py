import pathlib,re
d=pathlib.Path(__file__).parent; root=d.parent
L=(root/'area-home.html').read_text().split('\n')
head='\n'.join(L[:93]).replace('<title>Home</title>','<title>Home, round two</title>')
tail='\n'.join(L[1667:])
parts=[(d/f).read_text() for f in ['part-layouts.html','part-blocks.html','part-states.html'] if (d/f).exists()]
styles=''.join(re.findall(r'<style>.*?</style>',p,re.S)[0] for p in parts if '<style>' in p)
bodies=[re.sub(r'<style>.*?</style>','',p,count=1,flags=re.S) for p in parts]
body='<body data-title="Home, round two" data-desc="A deeper second batch for Home only: six new whole-page layouts, the three building blocks on their own (the top of Home, sessions, what happened and what is next), and Home when something needs you, on a first visit, after the close and on the phone.">'
(root/'area-home-2.html').write_text(head+'\n'+styles+'\n</head>\n'+body+'\n'+'\n'.join(bodies)+'\n'+tail)
print('ok',len(parts))
