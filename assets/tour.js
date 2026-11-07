"use strict";
const steps=[
  {
    "key": "play",
    "title": "Set up a round",
    "caption": "Choose an alias, a practice profile and a seed in Play & record."
  },
  {
    "key": "record",
    "title": "Watch the recorder",
    "caption": "The recorder receives the original trial data. At 20 seconds, it has received 694 records."
  },
  {
    "key": "review",
    "title": "Inspect a finding",
    "caption": "At 20.006 seconds, compare the recorded movement with its allowance."
  },
  {
    "key": "explain",
    "title": "Open the evidence card",
    "caption": "Attached as E1 opens the cited card. Back to replay returns to the same moment."
  },
  {
    "key": "export",
    "title": "Export the report",
    "caption": "Check the evidence, review the draft status and export the HTML report."
  }
];
const buttons=[...document.querySelectorAll('.tournav button')];
const toggle=document.getElementById('autoplay');
let selected=0,timer=null;
function show(index){selected=index;const step=steps[index];document.getElementById('screen').src='assets/'+step.key+'.png';document.getElementById('screen').alt=step.title+' — captured Surge interface';document.getElementById('title').textContent=step.title;document.getElementById('caption').textContent=step.caption;document.getElementById('position').textContent=(index+1)+' / '+steps.length;buttons.forEach((b,i)=>b.setAttribute('aria-pressed',String(i===index)));}
function stop(){clearInterval(timer);timer=null;toggle.textContent='Play two-minute tour';toggle.setAttribute('aria-pressed','false');}
buttons.forEach((button,index)=>button.addEventListener('click',()=>{stop();show(index);}));
document.querySelector('.tournav').addEventListener('keydown',event=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;event.preventDefault();stop();const next=event.key==='Home'?0:event.key==='End'?steps.length-1:(selected+(event.key==='ArrowRight'?1:-1)+steps.length)%steps.length;show(next);buttons[next].focus();});
toggle.addEventListener('click',()=>{if(timer){stop();return;}show(0);toggle.textContent='Pause tour';toggle.setAttribute('aria-pressed','true');timer=setInterval(()=>{if(selected===steps.length-1)stop();else show(selected+1);},24000);});
document.addEventListener('visibilitychange',()=>{if(document.hidden)stop();});
