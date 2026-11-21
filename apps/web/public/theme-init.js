(function(){var d=document.documentElement,s={},q,v;try{v=JSON.parse(localStorage.getItem('llamatrade-theme')||'{}');s=v.state||{};if((v.version|0)<2){if(s.darkAccent==='slate')s.darkAccent='';if(s.lightAccent==='ocean')s.lightAccent=''}}catch(e){}
var D='neutral silver white orange lime teal cyan blue slate indigo violet lilac pink'.split(' '),L='neutral charcoal ink rust pine teal ocean blue navy slate iris plum burgundy'.split(' ');
var m=s.mode==='light'||s.mode==='dark'?s.mode:s.mode==='system'?'':d.getAttribute('data-mode-default')||'';
if(!m){try{q=matchMedia('(prefers-color-scheme: light)').matches}catch(e){q=false}m=q?'light':'dark'}
d.setAttribute('data-mode',m);d.setAttribute('data-theme',s.darkSurface==='black'?'black':'slate');d.setAttribute('data-light',s.lightSurface==='warm'?'warm':'white');
var a=m==='dark'?s.darkAccent:s.lightAccent,A=m==='dark'?D:L;d.setAttribute('data-acc',A.indexOf(a)>=0?a:'neutral')})();
