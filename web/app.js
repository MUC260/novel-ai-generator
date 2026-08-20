(function(){'use strict';
var _d=document,_w=window;
var $=function(id){return _d.getElementById(id);};
var esc=function(s){return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');};
var api=async function(p,o){var r=await fetch(p,o);var d=await r.json().catch(function(){return{};});if(!r.ok||d.ok===false)throw new Error(d.error||'Err '+r.status);return d;};
var toast=function(m){var t=$('toast'),s=$('toastText');if(!t||!s)return;s.textContent=m;t.classList.remove('hidden');clearTimeout(t._t);t._t=setTimeout(function(){t.classList.add('hidden');},3500);};
var setStatus=function(text,ok){var e=$('statusText');if(e)e.textContent=text;var d=$('statusDot');if(d){d.style.background=(ok==='warn')?'var(--warn)':(ok?'var(--ok)':'var(--danger)');}
var wrap=$('statusLeft');if(wrap){if(ok==='warn'){wrap.classList.add('clickable');wrap.onclick=openSettings;}else{wrap.classList.remove('clickable');wrap.onclick=null;}}};
var setOnclick=function(id,fn){var el=$(id);if(!el){console.warn('#'+id+' not found');return;}el.onclick=fn;};

// ====== 导航切换 ======
_d.querySelectorAll('.nav-item').forEach(function(b){b.addEventListener('click',function(){
_d.querySelectorAll('.nav-item').forEach(function(x){x.classList.remove('active');});
_d.querySelectorAll('.panel').forEach(function(x){x.classList.remove('active');x.classList.add('hidden');});
b.classList.add('active');var t=$('tab-'+b.dataset.tab);if(t){t.classList.remove('hidden');t.classList.add('active');}
if(b.dataset.tab==='projects')loadProjectList();
if(b.dataset.tab==='continue')loadProjectsSelect();
});});

// ====== 状态栏 ======
var _currentModel='';
var refreshHealth=async function(){
try{
var d=await api('/api/health');
_currentModel=d.model||'';
updateHeaderModelSelect(_currentModel);
if(d.configured||d.api_key_set||d.status==='configured'){setStatus('OK: '+(d.model||'已连接'),true);}
else{setStatus('未配置密钥 · 点击设置','warn');}
}catch(e){setStatus('Err: '+e.message,false);}};
setOnclick('testBtn',async function(){this.disabled=true;this.textContent='测试中...';
try{var d=await api('/api/test',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});setStatus('Test: '+(d.reply||'OK'),true);}
catch(e){setStatus('Test fail: '+e.message,false);}
finally{this.disabled=false;this.textContent='🧪 测试模型';}});
setOnclick('refreshBtn',function(){refreshHealth();loadModels();loadProjectsSelect();loadProjectList();});

// ====== 设置（模型切换 + 密钥快速接入） ======
var _modelsCache=[];
var loadModels=async function(){
try{var d=await api('/api/models');_modelsCache=d.models||[];}
catch(e){_modelsCache=[];}
fillHeaderModelSelect(_currentModel);
fillSettingsModelSelect(_currentModel);
};
var fillHeaderModelSelect=function(cur){
var sel=$('headerModelSelect');if(!sel)return;
var opts='<option value="">模型</option>',seen={};
var add=function(m){if(!m||seen[m])return;seen[m]=1;opts+='<option value="'+esc(m)+'">'+esc(m)+'</option>';};
add(cur);
for(var i=0;i<_modelsCache.length;i++)add(_modelsCache[i]);
sel.innerHTML=opts;sel.value=cur||'';
};
var updateHeaderModelSelect=function(cur){
var sel=$('headerModelSelect');if(!sel)return;
if(!cur){sel.value='';return;}
var found=false;
for(var i=0;i<sel.options.length;i++){if(sel.options[i].value===cur){found=true;break;}}
if(!found){var o=_d.createElement('option');o.value=cur;o.textContent=cur;sel.appendChild(o);}
sel.value=cur;
};
var fillSettingsModelSelect=function(cur){
var sel=$('settingsModelSelect');if(!sel)return;
var opts='',seen={};
var add=function(m){if(!m||seen[m])return;seen[m]=1;opts+='<option value="'+esc(m)+'">'+esc(m)+'</option>';};
add(cur);
for(var i=0;i<_modelsCache.length;i++)add(_modelsCache[i]);
opts+='<option value="__custom__">✏️ 自定义模型</option>';
sel.innerHTML=opts;
var isCustom=cur&&!seen[cur];
var cw=$('settingsCustomWrap'),cm=$('settingsCustomModel');
if(isCustom){sel.value='__custom__';if(cw)cw.classList.remove('hidden');if(cm)cm.value=cur;}
else{sel.value=cur||'';if(cw)cw.classList.add('hidden');if(cm)cm.value=cur||'';}
};
var loadSettingsIntoModal=async function(){
var d=await api('/api/settings');
var bu=$('settingsBaseUrl'),key=$('settingsApiKey'),hint=$('settingsKeyStatus'),src=$('settingsSourceText');
if(bu)bu.value=d.base_url||'';
if(key){key.value='';key.placeholder='未配置则使用离线模式';}
if(hint)hint.textContent=d.api_key_set?('✅ 已配置：'+(d.api_key_masked||'sk-****')):'未配置密钥（将使用离线模式）';
if(src)src.textContent=d.source==='runtime'?'密钥来源：runtime（本次运行填写）':'密钥来源：env（内置 .env）';
if(d.model)_currentModel=d.model;
fillSettingsModelSelect(d.model||'');
};
var openSettings=async function(){
var m=$('settingsModal');if(!m)return;
m.classList.remove('hidden');
var tr=$('settingsTestResult');if(tr)tr.textContent='';
try{await loadModels();await loadSettingsIntoModal();}
catch(e){toast('加载设置失败: '+e.message);}
};
setOnclick('settingsBtn',openSettings);
setOnclick('closeSettings',function(){$('settingsModal').classList.add('hidden');});
setOnclick('settingsKeyToggle',function(){
var key=$('settingsApiKey');if(!key)return;
key.type=key.type==='password'?'text':'password';
this.textContent=key.type==='password'?'👁':'🙈';
});
var _settingsSel=$('settingsModelSelect');
if(_settingsSel){_settingsSel.addEventListener('change',function(){
if(this.value==='__custom__'){var cw=$('settingsCustomWrap');if(cw)cw.classList.remove('hidden');var cm=$('settingsCustomModel');if(cm)cm.focus();}
else{var cw2=$('settingsCustomWrap');if(cw2)cw2.classList.add('hidden');var cm2=$('settingsCustomModel');if(cm2)cm2.value=this.value;}
});}
var getSelectedModel=function(){
var sel=$('settingsModelSelect');if(!sel)return'';
if(sel.value==='__custom__'){var cm=$('settingsCustomModel');return cm?cm.value.trim():'';}
return sel.value||'';
};
setOnclick('settingsTestBtn',async function(){
var btn=this;btn.disabled=true;btn.textContent='测试中...';
var tr=$('settingsTestResult');if(tr)tr.textContent='';
try{
var d=await api('/api/test',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
setStatus('Test: '+(d.reply||'OK'),true);
if(tr){tr.textContent='✅ 连接成功：'+(d.reply||'OK');tr.className='settings-test-result ok';}
}catch(e){
setStatus('Test fail: '+e.message,false);
if(tr){tr.textContent='❌ 连接失败：'+e.message;tr.className='settings-test-result err';}
}finally{btn.disabled=false;btn.textContent='🧪 测试连接';}
});
setOnclick('settingsSaveBtn',async function(){
var btn=this;btn.disabled=true;btn.textContent='保存中...';
var body={},bu=$('settingsBaseUrl'),key=$('settingsApiKey');
if(bu&&bu.value.trim())body.base_url=bu.value.trim();
if(key&&key.value.trim())body.api_key=key.value.trim();
var model=getSelectedModel();
if(model)body.model=model;
try{
var d=await api('/api/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
toast('设置已保存');
if(d.model)_currentModel=d.model;
refreshHealth();
await loadSettingsIntoModal();
}catch(e){toast('保存失败: '+e.message);}
finally{btn.disabled=false;btn.textContent='💾 保存';}
});
setOnclick('settingsResetBtn',async function(){
var btn=this;btn.disabled=true;btn.textContent='恢复中...';
try{
await api('/api/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({clear_api_key:true,base_url:'',model:''})});
toast('已恢复默认(.env)');
_currentModel='';
refreshHealth();
await loadSettingsIntoModal();
}catch(e){toast('恢复失败: '+e.message);}
finally{btn.disabled=false;btn.textContent='恢复默认(.env)';}
});
// 顶部快捷模型切换器：切换即保存并刷新状态
var _headerSel=$('headerModelSelect');
if(_headerSel){_headerSel.addEventListener('change',function(){
var m=this.value;if(!m)return;
(async function(){
try{
await api('/api/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({model:m})});
_currentModel=m;toast('已切换模型: '+m);refreshHealth();
}catch(e){toast('切换失败: '+e.message);refreshHealth();}
})();
});}

// ====== 新建工程 ======
var collectCreate=function(){return{
title:$('title').value.trim(),mode:$('mode').value,genre:'',style:'',world:'',rules:'',power:'',forces:'',
protagonist:$('protagonist').value.trim(),side_characters:'',antagonist:'',opening:'',conflict:'',relations:'',direction:'',taboos:'',preferences:'',
worldview:$('worldview').value.trim(),
chapters:Number($('chapters').value),tier:$('tier').value,
anti_ending:$('anti_ending').checked,memory_inherit:$('memory_inherit').checked,progression:$('progression').checked,de_ai:$('de_ai').checked,autosave:$('autosave').checked};};
(function(){var sel=$('chapters');if(!sel)return;for(var i=1;i<=15;i++){var o=_d.createElement('option');o.value=i;o.textContent=i+'章';if(i===5)o.selected=true;sel.appendChild(o);}})();
var _currentProjectName='';
var addGenHint=function(anchor,text){
var d=_d.createElement('div');d.className='gen-hint';
d.innerHTML='<span class="spinner"></span> '+esc(text);
anchor.parentNode.insertBefore(d,anchor);
return d;
};
setOnclick('createStep1Next',async function(){var body=collectCreate();if(!body.title){toast('请填写小说名称');return;}
this.disabled=true;this.textContent='正在生成世界观...';
var hint=addGenHint(this,'正在生成世界观，请耐心等待...');
try{var d=await api('/api/world/generate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
_currentProjectName=body.title;renderArchivePreview(d.project);$('createStep1').classList.add('hidden');$('createStep2').classList.remove('hidden');
}catch(e){toast('生成失败: '+e.message);}finally{this.disabled=false;this.textContent='生成世界档案 →';if(hint)hint.remove();}});
var renderArchivePreview=function(p){var el=$('archivePreview');if(!el)return;
var w=p.world||{};var ws=w.world_setting||{};var chars=(p.char&&p.char.characters)||[];var plot=p.plot||{};
var h='<div class="archive-card">';
h+='<h3>'+esc(p.title||p.name)+'</h3>';
h+='<div class="archive-meta">';
h+='<span>世界类型: '+esc(ws['世界类型']||'未设定')+'</span>';
h+='<span>主角: '+esc(chars.length?chars[0]['姓名']||'(待生成)':'(待生成)')+'</span>';
h+='<span>共 '+(p.chapters?p.chapters.length:'0')+' 章</span></div>';
h+='<details><summary>世界观设定</summary><pre>'+esc(JSON.stringify(ws,null,2))+'</pre></details>';
h+='<details><summary>人物档案</summary><pre>'+esc(JSON.stringify(p.char||{},null,2))+'</pre></details>';
h+='<details><summary>剧情纲要</summary><pre>'+esc(JSON.stringify(plot,null,2))+'</pre></details></div>';el.innerHTML=h;};
setOnclick('step2Back',function(){$('createStep2').classList.add('hidden');$('createStep1').classList.remove('hidden');});
setOnclick('step2Next',async function(){var body=collectCreate();var name=$('title').value.trim();if(!name){toast('请先完成第一步');return;}
this.disabled=true;this.textContent='正在生成大纲...';
var hint=addGenHint(this,'正在生成大纲，请耐心等待...');
try{var d=await api('/api/outline/generate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:name,chapters:Number($('chapters').value),tier:$('tier').value})});
var outline=d.outline||{};var items=outline.outline||[];
var h='<div class="outline-list">';for(var i=0;i<items.length;i++){var o=items[i];
h+='<div class="outline-chapter">';
h+='<div class="outline-chapter-title">第'+(i+1)+'章：'+esc(o.title||'')+'</div>';
h+='<div class="outline-chapter-summary">'+esc(o.summary||'')+'</div>';
h+='</div>';}h+='</div>';
if(items.length){h+='<textarea id="outlineEditor" class="outline-editor">'+esc(JSON.stringify(outline,null,2))+'</textarea>';}
$('outlineContainer').innerHTML=h;$('outlineLoading').classList.add('hidden');$('outlineContainer').classList.remove('hidden');$('createStep2').classList.add('hidden');$('createStepOutline').classList.remove('hidden');
}catch(e){toast('生成大纲失败: '+e.message);}finally{this.disabled=false;this.textContent='生成大纲 →';if(hint)hint.remove();}});
setOnclick('outlineRegenBtn',function(){$('outlineLoading').classList.remove('hidden');$('outlineContainer').classList.add('hidden');$('step2Next').click();});
setOnclick('outlineConfirmBtn',async function(){var outlineText=$('outlineEditor');if(outlineText){try{JSON.parse(outlineText.value);toast('大纲已确认，开始生成正文...');}catch(e){toast('大纲JSON格式有误，请检查');return;}}
var name=$('title').value.trim();if(!name)return;var body=collectCreate();
this.disabled=true;this.textContent='正在生成...';
$('createStepOutline').classList.add('hidden');$('createStep3').classList.remove('hidden');
$('progressFill').style.width='0%';$('progressText').textContent='准备中...';$('progressLog').innerHTML='';var st=$('chapterStatus');if(st)st.innerHTML='';var _heartbeat=setInterval(function(){var cur=parseFloat($('progressFill').style.width)||0;if(cur<85){$('progressFill').style.width=Math.min(85,cur+Math.floor(Math.random()*6)+3)+'%';}},600);
try{var r=await fetch('/api/chapters/generate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
var reader=r.body.getReader(),dec=new TextDecoder(),buf='',results=[],projName='';
while(true){var{done,value}=await reader.read();if(done)break;buf+=dec.decode(value,{stream:true});var lines=buf.split('\n');buf=lines.pop();
for(var idx=0;idx<lines.length;idx++){var line=lines[idx];if(!line.trim())continue;
try{var c=JSON.parse(line);
if(c.type==='progress'){var pct=Math.round(c.percent||(c.total?c.chapter/c.total*100:0))||0;if(!isFinite(pct)||pct<0)pct=0;if(pct>100)pct=100;$('progressFill').style.width=pct+'%';$('progressText').textContent='正在生成第 '+c.chapter+' 章...';var log=$('progressLog');if(log){log.innerHTML+='<div>📝 正在生成第 '+c.chapter+' 章...</div>';log.scrollTop=log.scrollHeight;}}
else if(c.type==='chapter'){var st2=$('chapterStatus');if(st2){var tag=_d.createElement('span');tag.className='chapter-tag done';tag.textContent='第'+c.chapter+'章 ✓';st2.appendChild(tag);}}
else if(c.type==='done'){clearInterval(_heartbeat);$('progressFill').style.width='100%';projName=body.title;results=c.results||[];window._lastResults=results;window._lastProjName=projName;$('createStep3').classList.add('hidden');$('createStep4').classList.remove('hidden');renderDoneResult(c);}
else if(c.type==='error'){clearInterval(_heartbeat);toast('第'+c.chapter+'章生成失败: '+c.error);}}catch(e){}}}
}catch(e){toast('生成失败: '+e.message);}finally{this.disabled=false;this.textContent='确认大纲';}});
setOnclick('outlineBackBtn',function(){$('createStepOutline').classList.add('hidden');$('createStep2').classList.remove('hidden');});
// ====== 续写工程 ======
var loadProjectsSelect=async function(){var sel=$('continueProject');if(!sel)return;
try{var d=await api('/api/projects');var opts='<option value="">请选择工程</option>';
for(var i=0;i<d.projects.length;i++){opts+='<option value="'+esc(d.projects[i])+'">'+esc(d.projects[i])+'</option>';}
sel.innerHTML=opts;}catch(e){toast('加载项目列表失败: '+e.message);}};
(function(){var sel=$('continueChapters');if(!sel)return;for(var i=1;i<=15;i++){var o=_d.createElement('option');o.value=i;o.textContent=i+'章';if(i===3)o.selected=true;sel.appendChild(o);}})();
setOnclick('continueBtn',async function(){var proj=$('continueProject');if(!proj||!proj.value){toast('请选择工程');return;}
var ch=$('continueChapters');var tier=$('continueTier');
this.disabled=true;this.textContent='续写中...';$('continueProgress').classList.remove('hidden');$('continueProgressFill').style.width='0%';$('continueProgressLabel').textContent='准备中...';$('continueProgressCount').textContent='0 / '+ch.value;var logEl=_d.getElementById('continueLog');if(logEl)logEl.innerHTML='';
var _continueHeartbeat=setInterval(function(){var cur=parseFloat(document.getElementById('continueProgressFill').style.width)||0;if(cur<85){document.getElementById('continueProgressFill').style.width=Math.min(85,cur+Math.floor(Math.random()*6)+3)+'%';}},600);try{var body={project:proj.value,chapters:Number(ch.value),tier:tier.value,anti_ending:($('continue_anti_ending')||{checked:true}).checked,memory_inherit:($('continue_memory_inherit')||{checked:true}).checked,progression:($('continue_progression')||{checked:true}).checked,de_ai:($('continue_de_ai')||{checked:true}).checked};
var r=await fetch('/api/continue',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
var reader=r.body.getReader(),dec=new TextDecoder(),buf='',results=[],projName='';
while(true){var{done,value}=await reader.read();if(done)break;buf+=dec.decode(value,{stream:true});var lines=buf.split('\n');buf=lines.pop();
for(var idx=0;idx<lines.length;idx++){var line=lines[idx];if(!line.trim())continue;
try{var c=JSON.parse(line);
if(c.type==='progress'){var pct=Math.round(c.percent||c.progress||(c.chapter&&c.total?c.chapter/c.total*100:0));if(!isFinite(pct)||pct<0)pct=0;if(pct>100)pct=100;$('continueProgressFill').style.width=pct+'%';$('continueProgressLabel').textContent='正在生成第 '+c.chapter+' 章...';$('continueProgressCount').textContent=c.chapter+' / '+c.total;var cgm=document.getElementById('continueGenMessage');if(cgm)cgm.textContent='正在生成第 '+c.chapter+' 章...';}
else if(c.type==='chapter'){var cpl=_d.getElementById('continueChapterProgressList');if(cpl){var ctag=_d.createElement('span');ctag.className='chapter-tag done';ctag.textContent='第'+c.chapter+'章 ✓';cpl.appendChild(ctag);}var logEl2=_d.getElementById('continueLog');if(logEl2){logEl2.innerHTML+='<div>✅ 第 '+c.chapter+' 章生成完成 ('+c.chars+' 字)</div>';logEl2.scrollTop=logEl2.scrollHeight;}}
else if(c.type==='done'){clearInterval(_continueHeartbeat);projName=body.project;results=c.results||[];window._lastResults=results;window._lastProjName=projName;$('continueProgress').classList.add('hidden');renderContinueResult(projName,results);}
else if(c.type==='error'){toast('第'+c.chapter+'章生成失败: '+c.error);var logEl3=_d.getElementById('continueLog');if(logEl3)logEl3.innerHTML+='<div style="color:var(--danger);">❌ 第 '+c.chapter+' 章失败: '+esc(c.error)+'</div>';}}catch(e){}}}
$('continueProgress').classList.add('hidden');
}catch(e){clearInterval(_continueHeartbeat);toast('续写失败: '+e.message);}finally{this.disabled=false;this.textContent='开始续写';}});

// ====== 工程查看 ======
var loadProjectList=async function(){var el=$('projectList'),cnt=$('projectCount');if(!el)return;
try{var d=await api('/api/projects');if(!d.projects||d.projects.length===0){el.innerHTML='<p style="color:var(--muted);">暂无工程</p>';if(cnt)cnt.textContent='共 0 个工程';return;}
if(cnt)cnt.textContent='共 '+d.projects.length+' 个工程';
var h='<div class="project-cards" id="projectCards">';for(var i=0;i<d.projects.length;i++){h+='<div class="project-card" data-project="'+esc(d.projects[i])+'"><span class="project-card-icon">📚</span><span class="project-card-name">'+esc(d.projects[i])+'</span><span class="project-card-arrow">›</span></div>';}h+='</div>';
el.innerHTML=h;
var pc=_d.getElementById('projectCards');if(pc){pc.addEventListener('click',function(e){var card=e.target.closest('.project-card');if(card&&card.dataset.project)showProjectDetail(card.dataset.project);});}}catch(e){el.innerHTML='<p style="color:var(--danger);">加载失败: '+esc(e.message)+'</p>';}};
var showProjectDetail=async function(name){var el=$('projectDetail');if(!el)return;
try{var d=await api('/api/project/stats?name='+encodeURIComponent(name));
var stats=d.stats||{};var chapters=stats.chapters||[];var total_chars=stats.total_chars||0;var chars_count=stats.chars_count||0;
if(typeof chapters==='number'){var chCount=chapters;chapters=[];for(var k=0;k<chCount;k++){chapters.push({chars:'?',index:k+1,name:'第 '+(k+1)+' 章'});}total_chars=stats.total_chars||0;}
var h='<div class="project-detail">';
h+='<div class="detail-header"><h3>'+esc(name)+'</h3>';
h+='<span class="stat-badge">📖 '+(chapters.length)+' 章</span>';
h+='<span class="stat-badge">📝 '+(total_chars)+' 字</span>';
h+='<span class="stat-badge">👤 '+(chars_count)+' 角色</span></div>';
h+='<div class="detail-actions" data-project="'+esc(name)+'">';
h+='<button class="btn btn-sm detail-action" data-action="reader">📖 沉浸式阅读</button>';
h+='<button class="btn btn-sm detail-action" data-action="export">⬇️ 导出</button>';
h+='<button class="btn btn-sm detail-action" data-action="delete">🗑️ 删除</button>';
h+='<button class="btn btn-sm detail-action" data-action="rename">✏️ 重命名</button></div>';
h+='<div class="chapter-list" data-project="'+esc(name)+'">';
if(chapters.length===0){h+='<p style="color:var(--muted);">暂无章节，请先生成正文</p>';}else{for(var j=0;j<chapters.length;j++){var ch=chapters[j];
h+='<div class="chapter-item" data-chapter-index="'+ch.index+'">';
h+='<span class="chapter-title">'+esc(ch.name)+'</span>';
h+='<span class="chapter-stats">'+(ch.chars||'?')+'字</span>';
h+='<span class="chapter-actions">';
h+='<button class="btn btn-sm chapter-action" data-action="view">查看</button>';
h+='<button class="btn btn-sm chapter-action" data-action="revise">修订</button>';
h+='<button class="btn btn-sm btn-danger chapter-action" data-action="delete-chapter">删除</button>';
h+='</span></div>';}}
h+='</div></div>';el.innerHTML=h;
var projectName=name;
var detailEl=el;
detailEl.addEventListener('click',function(e){
var target=e.target.closest('.detail-action, .chapter-action, .chapter-item');
if(!target)return;
var action=target.dataset.action;
var proj=detailEl.querySelector('.detail-actions')?.dataset?.project||projectName;
if(action==='reader'){openReader(proj);}
else if(action==='export'){exportProject(proj);}
else if(action==='delete'){deleteProject(proj);}
else if(action==='rename'){renameProject(proj);}
else if(action==='view'){var idx=target.closest('.chapter-item')?.dataset?.chapterIndex;if(idx)viewChapter(proj,parseInt(idx));}
else if(action==='revise'){var idx=target.closest('.chapter-item')?.dataset?.chapterIndex;if(idx)showRevise(proj,parseInt(idx));}
else if(action==='delete-chapter'){var idx=target.closest('.chapter-item')?.dataset?.chapterIndex;if(idx)deleteChapter(proj,parseInt(idx));}
else if(target.classList.contains('chapter-item')){var idx=target.dataset.chapterIndex;if(idx)viewChapter(proj,parseInt(idx));}
});}catch(e){el.innerHTML='<p class="text-danger">加载失败: '+esc(e.message)+'</p>';}};
var viewChapter=async function(proj,idx){try{var d=await api('/api/chapter?project='+encodeURIComponent(proj)+'&index='+idx);var txt=d.text||'';showChapterPreview(proj,idx,txt);}catch(e){toast('加载失败: '+e.message);}};
var showChapterPreview=function(proj,idx,txt){var el=$('chapterPreview');if(!el)return;
var h='<div class="modal-box chapter-preview-box">';
h+='<div class="modal-header"><span class="modal-title">📖 '+esc(proj)+' - 第'+idx+'章</span>';
h+='<button class="btn btn-ghost modal-close" data-close="1">✕</button></div>';
h+='<div class="modal-body chapter-preview-body">'+esc(txt)+'</div></div>';
el.innerHTML=h;el.classList.remove('hidden');};
var closeChapterPreview=function(){var el=$('chapterPreview');if(el)el.classList.add('hidden');};

// ====== 生成结果页 ======
var renderDoneResult=function(d){var el=$('resultChapters');if(!el)return;
var results=d.results||[];var projName=d.project?d.project.title||_currentProjectName:_currentProjectName;
var h='<div class="done-chapters" id="doneChapters">';
for(var i=0;i<results.length;i++){var r=results[i];
h+='<div class="done-chapter">';
h+='<span class="done-chapter-title">第'+(r.chapter||(i+1))+'章</span>';
h+='<span class="done-chapter-chars">'+(r.chars||'0')+'字</span>';
h+='<span class="done-chapter-actions">';
h+='<button class="btn btn-sm" data-action="copy" data-index="'+i+'">复制章节</button>';
h+='<button class="btn btn-sm" data-action="view" data-index="'+i+'">查看章节</button>';
h+='</span></div>';}
h+='</div>';el.innerHTML=h;
$('createStep3').classList.add('hidden');$('createStep4').classList.remove('hidden');
var legacy=$('createDoneResult');if(legacy)legacy.classList.add('hidden');
window._lastResults=results;window._lastProjName=projName;
var wrap=$('doneChapters');
if(wrap){wrap.addEventListener('click',function(e){var b=e.target.closest('button[data-action]');if(!b)return;var idx=parseInt(b.dataset.index,10);if(b.dataset.action==='copy')copyChapterText(idx);else if(b.dataset.action==='view')viewChapterResult(idx);});}};
var copyChapterText=function(i){var r=(window._lastResults||[])[i];if(!r)return;navigator.clipboard.writeText(r.text||'').then(function(){toast('已复制第'+(r.chapter||i+1)+'章');}).catch(function(){toast('复制失败');});};
var viewChapterResult=function(i){var r=(window._lastResults||[])[i];if(!r)return;showChapterPreview(window._lastProjName,i,r.text||'');};
var resetCreate=function(){$('createStep4').classList.add('hidden');$('createStep1').classList.remove('hidden');$('createStep2').classList.add('hidden');$('createStepOutline').classList.add('hidden');$('createStep3').classList.add('hidden');$('title').value='';$('protagonist').value='';$('worldview').value='';var _cr=$('continueResult');if(_cr){_cr.classList.add('hidden');_cr.innerHTML='';}var _pd=$('projectDetail');if(_pd)_pd.innerHTML='';var _rc=$('resultChapters');if(_rc)_rc.innerHTML='';};
// ====== 确认对话框 ======
var _confirmCb=null;
var showConfirm=function(title,msg,cb){$('confirmTitle').textContent=title;$('confirmMessage').textContent=msg;$('confirmModal').classList.remove('hidden');if(typeof cb==='function')_confirmCb=cb;else _confirmCb=null;};
setOnclick('closeConfirm',function(){$('confirmModal').classList.add('hidden');_confirmCb=null;});
setOnclick('confirmCancelBtn',function(){$('confirmModal').classList.add('hidden');_confirmCb=null;});
setOnclick('confirmOkBtn',function(){if(typeof _confirmCb==='function')_confirmCb();$('confirmModal').classList.add('hidden');_confirmCb=null;});

// ====== 重命名 ======
var _renameTarget='';
var renameProject=function(name){_renameTarget=name;$('renameInput').value=name;$('renameModal').classList.remove('hidden');};
setOnclick('closeRename',function(){$('renameModal').classList.add('hidden');});
setOnclick('renameCancelBtn',function(){$('renameModal').classList.add('hidden');});
setOnclick('renameOkBtn',async function(){var newName=$('renameInput').value.trim();if(!newName){toast('请输入新名称');return;}
try{await api('/api/project/rename',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({old:_renameTarget,new:newName})});
toast('重命名成功');$('renameModal').classList.add('hidden');loadProjectList();}catch(e){toast('重命名失败: '+e.message);}});

// ====== 删除 ======
var deleteProject=function(name){showConfirm('确认删除','确定要删除工程「'+name+'」吗？此操作不可恢复。',async function(){try{await api('/api/project/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:name})});toast('已删除');loadProjectList();}catch(e){toast('删除失败: '+e.message);}});};
var deleteChapter=function(proj,idx){showConfirm('确认删除','确定要删除第'+idx+'章吗？',async function(){try{await api('/api/chapter/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({project:proj,index:idx})});toast('已删除');showProjectDetail(proj);}catch(e){toast('删除失败: '+e.message);}});};

// ====== 修订 ======
var _reviseProject='',_reviseIdx=0;
var showRevise=function(proj,idx){_reviseProject=proj;_reviseIdx=parseInt(idx);$('reviseModal').classList.remove('hidden');$('reviseResult').classList.add('hidden');$('reviseInstructions').value='';};
setOnclick('closeRevise',function(){$('reviseModal').classList.add('hidden');});
setOnclick('reviseCancelBtn',function(){$('reviseModal').classList.add('hidden');});
setOnclick('reviseOkBtn',async function(){var inst=$('reviseInstructions').value.trim();if(!inst){toast('请输入修改意见');return;}
this.disabled=true;this.textContent='修订中...';
try{var d=await api('/api/chapter/revise',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({project:_reviseProject,index:_reviseIdx,instructions:inst})});
$('reviseOriginalText').textContent=(d.original||'').slice(0,500);$('reviseNewText').textContent=(d.text||'').slice(0,500);
$('reviseResult').classList.remove('hidden');toast('修订完成！');}catch(e){toast('修订失败: '+e.message);}
finally{this.disabled=false;this.textContent='确认修订';}});

// ====== 导出 ======
var exportProject=async function(name){try{var d=await api('/api/project/export?name='+encodeURIComponent(name));downloadText(d.text||d,name+'.txt');toast('导出成功');}catch(e){toast('导出失败: '+e.message);}};
var downloadText=function(text,name){var a=_d.createElement('a');a.href='data:text/plain;charset=utf-8,'+encodeURIComponent(text);a.download=name;_d.body.appendChild(a);a.click();_d.body.removeChild(a);};

// ====== 阅读器 ======
var _readerData=null,_readerIdx=0,_readerFont=17,_readerTheme='dark';
var applyReaderTheme=function(t){
_readerTheme=t;var rv=$('readerView');if(!rv)return;
['light','sepia','dark','green'].forEach(function(x){rv.classList.remove('theme-'+x);});
rv.classList.add('theme-'+t);
};
var openReader=async function(name){try{var d=await api('/api/project/book?name='+encodeURIComponent(name));
_readerData=d.book;_readerIdx=0;$('readerView').classList.remove('hidden');
applyReaderTheme(_readerTheme);
renderReaderChapter(0);}catch(e){toast('加载失败: '+e.message);}};
setOnclick('readerBack',function(){$('readerView').classList.add('hidden');_readerData=null;});
var renderReaderChapter=function(i){if(!_readerData||!_readerData.chapters||i<0||i>=_readerData.chapters.length)return;
_readerIdx=i;var ch=_readerData.chapters[i];
$('readerTitle').textContent=_readerData.name+' - '+ch.title;
var bh=$('readerBookHeader');
if(bh){bh.innerHTML='<div class="reader-book-title">'+esc(_readerData.name)+'</div><div class="reader-book-meta">共 '+_readerData.chapters.length+' 章</div>';}
$('readerChapterTitle').textContent=ch.title;
$('readerChapterBody').innerHTML='<p>'+esc(ch.text).replace(/\n/g,'<br>')+'</p>';
$('readerProgress').textContent=(i+1)+'/'+_readerData.chapters.length;
$('readerProgressFill').style.width=(((i+1)/_readerData.chapters.length)*100)+'%';
$('readerFullText').value=_readerData.chapters.map(function(c){return c.text;}).join('\n\n');
renderToc(_readerData.chapters,i);};
var renderToc=function(chapters,active){var el=$('readerTocList');if(!el)return;
var h='';for(var j=0;j<chapters.length;j++){h+='<div class="toc-item'+(j===active?' active':'')+'" data-index="'+j+'">'+esc(chapters[j].title)+'</div>';}
el.innerHTML=h;};
window._readerRenderChapter=function(j){renderReaderChapter(j);};
setOnclick('readerPrev',function(){if(_readerIdx>0)renderReaderChapter(_readerIdx-1);});
setOnclick('readerNext',function(){if(_readerIdx<_readerData.chapters.length-1)renderReaderChapter(_readerIdx+1);});
setOnclick('fontMinus',function(){if(_readerFont>12){_readerFont--;$('readerChapterBody').style.fontSize=_readerFont+'px';$('fontSizeDisplay').textContent=_readerFont;}});
setOnclick('fontPlus',function(){if(_readerFont<28){_readerFont++;$('readerChapterBody').style.fontSize=_readerFont+'px';$('fontSizeDisplay').textContent=_readerFont;}});
_d.querySelectorAll('.theme-dot').forEach(function(dot){dot.addEventListener('click',function(){var t=this.dataset.theme;applyReaderTheme(t);
_d.querySelectorAll('.theme-dot').forEach(function(x){x.classList.remove('active');});this.classList.add('active');});});
setOnclick('readerDownload',function(){if(_readerData){var txt=_readerData.chapters.map(function(c){return c.title+'\n'+c.text;}).join('\n\n');downloadText(txt,_readerData.name+'.txt');}});
setOnclick('readerCopyAll',function(){if(_readerData){var txt=_readerData.chapters.map(function(c){return c.title+'\n'+c.text;}).join('\n\n');navigator.clipboard.writeText(txt).then(function(){toast('已复制');}).catch(function(){toast('复制失败');});}});
_d.addEventListener('keydown',function(e){if(!_readerData||$('readerView').classList.contains('hidden'))return;
if(e.key==='ArrowLeft'){e.preventDefault();if(_readerIdx>0)renderReaderChapter(_readerIdx-1);}
else if(e.key==='ArrowRight'){e.preventDefault();if(_readerIdx<_readerData.chapters.length-1)renderReaderChapter(_readerIdx+1);}
else if(e.key==='Escape'){$('readerView').classList.add('hidden');_readerData=null;}});
var _tocEl=$('readerTocList');
if(_tocEl){_tocEl.addEventListener('click',function(e){var t=e.target.closest('.toc-item');if(t){var idx=parseInt(t.dataset.index,10);if(!isNaN(idx))renderReaderChapter(idx);}});}

// ====== 续写结果渲染 ======
var renderContinueResult=function(projName,results){var el=document.getElementById('continueResult');if(!el)return;
var h='<div class="continue-result">';
h+='<h3>✅ 续写完成</h3>';
h+='<p class="result-meta">工程: '+esc(projName)+' — 共 '+results.length+' 章</p>';
h+='<div class="result-nav">';
h+='<button class="btn btn-sm" data-action="reader">📖 沉浸式阅读</button>';
h+='<button class="btn btn-sm" data-action="export">⬇️ 导出</button>';
h+='<button class="btn btn-sm" data-action="copyall">📋 复制全部</button>';
h+='</div>';
h+='<div class="done-chapters">';
for(var i=0;i<results.length;i++){var r=results[i];
h+='<div class="done-chapter">';
h+='<span class="done-chapter-title">第'+(r.chapter||(i+1))+'章</span>';
h+='<span class="done-chapter-chars">'+(r.chars||'0')+'字</span>';
h+='<span class="done-chapter-actions">';
h+='<button class="btn btn-sm" data-action="copy" data-index="'+i+'">复制章节</button>';
h+='<button class="btn btn-sm" data-action="view" data-index="'+i+'">查看章节</button>';
h+='</span></div>';}
h+='</div></div>';el.innerHTML=h;el.classList.remove('hidden');
window._lastResults=results;window._lastProjName=projName;
var root=el.querySelector('.continue-result');
if(root){root.addEventListener('click',function(e){
var b=e.target.closest('button[data-action]');if(!b)return;
var a=b.dataset.action;
if(a==='reader')openReader(projName);
else if(a==='export')exportProject(projName);
else if(a==='copyall')window._copyAll();
else if(a==='copy')copyChapterText(parseInt(b.dataset.index,10));
else if(a==='view')viewChapterResult(parseInt(b.dataset.index,10));
});}};
window._copyAll=function(){var rs=window._lastResults||[];if(!rs.length){toast('没有内容');return;}var txt=rs.map(function(r){return '第'+(r.chapter||0)+'章\n'+r.text;}).join('\n\n');navigator.clipboard.writeText(txt).then(function(){toast('已复制');}).catch(function(){toast('复制失败');});};

// ====== 初始化 ======
$('readerView').classList.add('hidden');var _createTab=$('tab-create');if(_createTab){document.querySelectorAll('.panel').forEach(function(p){p.classList.remove('active');p.classList.add('hidden');});_createTab.classList.remove('hidden');_createTab.classList.add('active');}
var _cp=$('chapterPreview');
if(_cp){_cp.addEventListener('click',function(e){if(e.target===_cp||e.target.closest('[data-close]'))_cp.classList.add('hidden');});}
refreshHealth();loadModels();
setTimeout(function(){try{loadProjectsSelect();}catch(e){toast('加载项目列表失败: '+e.message);}try{loadProjectList();}catch(e){toast('加载工程列表失败: '+e.message);}},100);
// 供动态 HTML 调用的全局函数
window.showProjectDetail=showProjectDetail;
window.openReader=openReader;
window.exportProject=exportProject;
window.deleteProject=deleteProject;
window.renameProject=renameProject;
window.viewChapter=viewChapter;
window.closeChapterPreview=closeChapterPreview;
window.copyChapterText=copyChapterText;
window.viewChapterResult=viewChapterResult;
window.showRevise=showRevise;
window.deleteChapter=deleteChapter;
})();
