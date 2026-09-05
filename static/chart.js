(function(){
  function fmt(n){return new Intl.NumberFormat('en-US',{maximumFractionDigits:0}).format(n)}
  function drawChart(canvas, data, type){
    const ctx=canvas.getContext('2d'), dpr=window.devicePixelRatio||1;
    const rect=canvas.getBoundingClientRect(); const W=Math.max(320,rect.width), H=Math.max(300,rect.height);
    canvas.width=W*dpr; canvas.height=H*dpr; ctx.setTransform(dpr,0,0,dpr,0,0); ctx.clearRect(0,0,W,H);
    const pad={l:58,r:20,t:30,b:48}; const cw=W-pad.l-pad.r, ch=H-pad.t-pad.b;
    const years=data.map(x=>String(x.year));
    if(!data.length){ctx.fillText('No chart data available.',20,30);return}
    if(type==='pie'){
      const dep=data.reduce((s,x)=>s+Number(x.paid||0),0), arr=data.reduce((s,x)=>s+Number(x.arrear||0),0), total=dep+arr;
      const cx=W/2, cy=H/2-5, r=Math.min(cw,ch)*.32; let start=-Math.PI/2;
      const vals=[['Deposit',dep],['Arrear',arr]];
      vals.forEach(v=>{const a=total?2*Math.PI*v[1]/total:0;ctx.beginPath();ctx.moveTo(cx,cy);ctx.arc(cx,cy,r,start,start+a);ctx.closePath();ctx.fillStyle=v[0]==='Deposit'?'#2563eb':'#dc2626';ctx.fill();ctx.strokeStyle='#fff';ctx.lineWidth=2;ctx.stroke();start+=a});
      ctx.fillStyle='#172033';ctx.font='bold 16px Arial';ctx.textAlign='center';ctx.fillText('All Years',cx,cy+r+36);
      ctx.textAlign='left'; ctx.font='14px Arial';
      vals.forEach((v,i)=>{const y=H-42+i*22;ctx.fillStyle=v[0]==='Deposit'?'#2563eb':'#dc2626';ctx.fillRect(18,y-11,12,12);ctx.fillStyle='#172033';ctx.fillText(v[0]+' ৳'+fmt(v[1]),38,y)})
      return;
    }
    const max=Math.max(1,...data.flatMap(x=>[Number(x.paid||0),Number(x.arrear||0)]));
    ctx.strokeStyle='#dbe3ef';ctx.lineWidth=1;ctx.font='11px Arial';ctx.fillStyle='#64748b';ctx.textAlign='right';
    for(let i=0;i<=4;i++){const y=pad.t+ch-(ch*i/4), val=max*i/4;ctx.beginPath();ctx.moveTo(pad.l,y);ctx.lineTo(W-pad.r,y);ctx.stroke();ctx.fillText('৳'+fmt(val),pad.l-8,y+4)}
    const xStep=cw/Math.max(1,data.length); ctx.textAlign='center';ctx.fillStyle='#334155';
    years.forEach((yr,i)=>ctx.fillText(yr,pad.l+xStep*(i+.5),H-20));
    if(type==='bar'){
      data.forEach((x,i)=>{const gx=pad.l+xStep*(i+.5), bw=Math.min(28,xStep*.28); [['paid','#2563eb',-bw*.55],['arrear','#dc2626',bw*.55]].forEach(([k,c,off])=>{const v=Number(x[k]||0), bh=ch*v/max;ctx.fillStyle=c;ctx.fillRect(gx+off,pad.t+ch-bh,bw*.9,bh)})});
    } else {
      [['paid','#2563eb'],['arrear','#dc2626']].forEach(([k,c])=>{ctx.strokeStyle=c;ctx.lineWidth=3;ctx.beginPath();data.forEach((x,i)=>{const px=pad.l+xStep*(i+.5), py=pad.t+ch-ch*Number(x[k]||0)/max;i?ctx.lineTo(px,py):ctx.moveTo(px,py)});ctx.stroke();ctx.fillStyle=c;data.forEach((x,i)=>{const px=pad.l+xStep*(i+.5),py=pad.t+ch-ch*Number(x[k]||0)/max;ctx.beginPath();ctx.arc(px,py,4,0,Math.PI*2);ctx.fill()})});
    }
    ctx.textAlign='left';ctx.font='12px Arial';[['Deposit','#2563eb'],['Arrear','#dc2626']].forEach((v,i)=>{ctx.fillStyle=v[1];ctx.fillRect(pad.l+i*110,pad.t-17,12,12);ctx.fillStyle='#334155';ctx.fillText(v[0],pad.l+18+i*110,pad.t-7)})
  }
  function init(){document.querySelectorAll('[data-year-chart]').forEach(box=>{const data=JSON.parse(box.dataset.yearChart||'[]'), select=box.querySelector('.chart-type-select'), canvas=box.querySelector('canvas');function render(){drawChart(canvas,data,select.value);localStorage.setItem('sp_chart_type',select.value)};const saved=localStorage.getItem('sp_chart_type');if(saved&&['bar','line','pie'].includes(saved))select.value=saved;select.addEventListener('change',render);render();window.addEventListener('resize',render)})}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();