(function(){
  function ago(d){ var s=Math.max(0,(Date.now()-d)/1000), u=[[86400,'day'],[3600,'hour'],[60,'minute']];
    for(var i=0;i<u.length;i++){ var n=Math.floor(s/u[i][0]); if(n) return n+' '+u[i][1]+(n===1?'':'s')+' ago'; } return 'just now'; }
  document.addEventListener('DOMContentLoaded',function(){
    var root=document.getElementById('tet'); if(!root) return;
    var pending=root.querySelector('table.tet-pending tbody'), settled=root.querySelector('table.tet-settled tbody');
    var bar=root.querySelector('.tet-bar'), form=bar.querySelector('form'), submit=bar.querySelector('.tet-submit');
    var count=bar.querySelector('.tet-count'), all=bar.querySelector('.tet-pickall');
    function rows(){ return [].slice.call(pending.rows); }
    function decide(r,d){
      if(d) r.setAttribute('data-decision',d); else r.removeAttribute('data-decision');
      [].forEach.call(r.querySelectorAll('.tet-decide button'),function(b){ b.classList.toggle('tet-on',b.getAttribute('data-d')===d); });
      tally();
    }
    function tally(){
      var a=0,j=0; rows().forEach(function(r){ var d=r.getAttribute('data-decision'); if(d==='accept') a++; else if(d==='reject') j++; });
      count.textContent=(a+j)?a+' to accept, '+j+' to reject':'';
      submit.disabled=!(a+j); submit.textContent=(a+j)?'Submit '+(a+j):'Submit';
      root.querySelector('.tet-pending-count').textContent=rows().length;
      root.querySelector('.tet-empty').hidden=rows().length>0;
    }
    pending.addEventListener('click',function(e){
      var b=e.target.closest&&e.target.closest('.tet-decide button'); if(!b) return;
      var r=b.closest('tr'), d=b.getAttribute('data-d'); decide(r,r.getAttribute('data-decision')===d?'':d);
    });
    all.addEventListener('change',function(){ rows().forEach(function(r){ r.querySelector('.tet-pick').checked=all.checked; }); });
    [].forEach.call(bar.querySelectorAll('button[data-bulk]'),function(b){
      b.addEventListener('click',function(){
        rows().forEach(function(r){ var c=r.querySelector('.tet-pick'); if(c.checked){ decide(r,b.getAttribute('data-bulk')); c.checked=false; } });
        all.checked=false;
      });
    });
    form.addEventListener('submit',function(e){
      var f=[]; rows().forEach(function(r){ var d=r.getAttribute('data-decision'); if(d) f.push(['d',r.getAttribute('data-proposal')+':'+d]); });
      if(!f.length){ e.preventDefault(); return; }
      [].forEach.call(form.querySelectorAll('input[name=d]'),function(i){ i.remove(); });
      f.forEach(function(p){ var i=document.createElement('input'); i.type='hidden'; i.name=p[0]; i.value=p[1]; form.appendChild(i); });
      if(!window.fetch||!window.URLSearchParams) return;
      e.preventDefault(); submit.disabled=true; submit.textContent='Applying...';
      fetch(form.action,{method:'POST',body:new URLSearchParams(f.concat([['ajax','1']])),credentials:'same-origin'}).then(function(r){
        if(!r.ok) throw new Error(r.status); return r.text();
      }).then(function(html){
        var tmp=document.createElement('tbody'); tmp.innerHTML=html;
        [].slice.call(tmp.rows).reverse().forEach(function(n){
          var old=pending.querySelector('tr[data-proposal="'+n.getAttribute('data-proposal')+'"]'); if(old) old.remove();
          n.classList.add('tet-just'); settled.insertBefore(n,settled.firstChild);
        });
        [].forEach.call(root.querySelectorAll('.tkt-ago[data-utc]'),function(e){
          var d=new Date(e.getAttribute('data-utc').replace(' ','T')+'Z'); if(!isNaN(d)) e.textContent=ago(d);
        });
        tally();
      }).catch(function(){ form.submit(); });
    });
    tally();
  });
})();
