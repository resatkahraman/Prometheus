LAB_UI = r"""
<!doctype html>
<html lang="tr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="color-scheme" content="dark">
  <title>Prometheus ⚡ — Agent Workspace</title>
  <style>
    :root{
      --bg:#08090d;
      --rail:#0b0c11;
      --surface:#101218;
      --surface-2:#151821;
      --surface-3:#1b1f29;
      --line:#252a36;
      --line-strong:#363d4c;
      --text:#f4f6fb;
      --text-2:#b5bccb;
      --text-3:#747d90;
      --blue:#6d7cff;
      --blue-2:#99a4ff;
      --cyan:#66d9e8;
      --green:#5de4a1;
      --amber:#ffc768;
      --red:#ff7d83;
      --radius:16px;
      --shadow:0 18px 55px rgba(0,0,0,.28);
    }
    *{box-sizing:border-box}
    html{background:var(--bg)}
    body{
      margin:0;
      min-width:320px;
      color:var(--text);
      background:
        radial-gradient(1200px 600px at 58% -200px,rgba(109,124,255,.18),transparent 70%),
        radial-gradient(800px 400px at 20% 100%,rgba(102,217,232,.08),transparent 60%),
        radial-gradient(600px 300px at 90% 50%,rgba(93,228,161,.06),transparent 50%),
        var(--bg);
      font:14px/1.5 Inter,ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
      -webkit-font-smoothing:antialiased;
      animation:bgShift 20s ease infinite;
    }
    @keyframes bgShift{
      0%,100%{background-position:0% 0%,0% 100%,100% 50%}
      50%{background-position:100% 0%,20% 80%,80% 60%}
    }
    button,input,textarea,select{font:inherit}
    button,a,select{touch-action:manipulation}
    button{color:inherit}
    a{color:inherit;text-decoration:none}
    :focus-visible{
      outline:2px solid #b9c1ff;
      outline-offset:3px;
    }
    ::selection{background:#6574ff55;color:#fff}
    ::-webkit-scrollbar{width:10px;height:10px}
    ::-webkit-scrollbar-thumb{background:#303644;border:3px solid transparent;background-clip:padding-box;border-radius:20px}

    .app{display:grid;grid-template-columns:224px minmax(0,1fr);min-height:100vh}
    .rail{
      position:sticky;top:0;height:100vh;z-index:20;
      display:flex;flex-direction:column;
      padding:22px 14px 16px;
      background:rgba(11,12,17,.96);
      border-right:1px solid var(--line);
      backdrop-filter:blur(18px);
    }
    .brand{display:flex;align-items:center;gap:11px;padding:0 9px 24px}
    .brand-mark{
      position:relative;width:35px;height:35px;display:grid;place-items:center;
      border:1px solid #4a5478;border-radius:11px;
      background:linear-gradient(145deg,#2a3048,#16182a);
      color:#dfe3ff;font-weight:800;letter-spacing:-.03em;
      box-shadow:
        inset 0 0 18px rgba(109,124,255,.22),
        0 4px 12px rgba(109,124,255,.15);
      animation:brandPulse 3s ease-in-out infinite;
    }
    @keyframes brandPulse{
      0%,100%{box-shadow:inset 0 0 18px rgba(109,124,255,.22),0 4px 12px rgba(109,124,255,.15)}
      50%{box-shadow:inset 0 0 24px rgba(109,124,255,.32),0 6px 18px rgba(109,124,255,.25)}
    }
    .brand-mark:after{
      content:"";position:absolute;width:6px;height:6px;right:-2px;top:-2px;
      border:2px solid var(--rail);border-radius:50%;background:var(--green);
      animation:pulse 2s cubic-bezier(0.4,0,0.6,1) infinite;
    }
    @keyframes pulse{
      0%,100%{opacity:1}
      50%{opacity:.5}
    }
    .brand-name{font-weight:740;letter-spacing:-.02em}
    .brand-version{font-size:10px;color:var(--text-3);letter-spacing:.08em;text-transform:uppercase}
    .nav-label,.rail-label{
      padding:0 10px 8px;color:#697185;font-size:10px;font-weight:700;
      letter-spacing:.12em;text-transform:uppercase;
    }
    .nav{display:grid;gap:4px}
    .nav-button{
      position:relative;width:100%;min-height:44px;display:flex;align-items:center;gap:11px;
      border:0;border-radius:11px;padding:0 11px;background:transparent;
      color:var(--text-3);font-weight:600;text-align:left;cursor:pointer;
      transition:all .2s cubic-bezier(0.4,0,0.2,1);
    }
    .nav-button svg{
      width:19px;height:19px;stroke:currentColor;fill:none;stroke-width:1.7;
      transition:transform .2s cubic-bezier(0.4,0,0.2,1);
    }
    .nav-button:hover{
      background:linear-gradient(135deg,rgba(109,124,255,.08),rgba(102,217,232,.04));
      color:var(--text);
      transform:translateX(2px);
    }
    .nav-button:hover svg{transform:scale(1.08)}
    .nav-button.active{
      background:linear-gradient(135deg,rgba(109,124,255,.14),rgba(102,217,232,.08));
      color:#fff;
      box-shadow:0 2px 8px rgba(109,124,255,.15);
    }
    .nav-button.active:before{
      content:"";position:absolute;left:-14px;top:11px;width:3px;height:22px;
      background:var(--blue-2);border-radius:0 4px 4px 0;
    }
    .nav-count{
      margin-left:auto;min-width:22px;height:20px;padding:0 6px;display:none;place-items:center;
      border-radius:20px;background:#584619;color:#ffe0a2;font-size:10px;
    }
    .nav-count.show{display:grid}
    .rail-bottom{margin-top:auto;display:grid;gap:12px}
    .system-tile{
      padding:12px;border:1px solid var(--line);border-radius:13px;background:#101218;
    }
    .system-line{display:flex;align-items:center;gap:8px;color:var(--text-2);font-size:12px}
    .pulse{width:7px;height:7px;border-radius:50%;background:var(--amber)}
    .pulse.online{background:var(--green);box-shadow:0 0 0 4px rgba(93,228,161,.08)}
    .system-detail{margin:5px 0 0 15px;color:var(--text-3);font-size:10px}
    .rail-links{display:flex;gap:6px}
    .rail-link{
      min-height:36px;flex:1;display:grid;place-items:center;border:1px solid var(--line);
      border-radius:9px;color:var(--text-3);font-size:11px;
    }
    .rail-link:hover{color:var(--text);border-color:var(--line-strong)}

    .workspace{min-width:0}
    .topbar{
      height:68px;display:flex;align-items:center;justify-content:space-between;gap:18px;
      padding:0 28px;border-bottom:1px solid var(--line);
      background:rgba(8,9,13,.73);backdrop-filter:blur(16px);
      position:sticky;top:0;z-index:15;
    }
    .crumb{display:flex;align-items:center;gap:8px;min-width:0;color:var(--text-3);font-size:12px}
    .crumb strong{color:var(--text-2);font-weight:600}
    .crumb-divider{color:#404655}
    .top-status{display:flex;align-items:center;gap:8px}
    .status-chip{
      min-height:30px;display:flex;align-items:center;gap:7px;padding:0 10px;
      border:1px solid var(--line);border-radius:9px;background:#101218;
      color:var(--text-3);font-size:11px;white-space:nowrap;
    }
    .status-chip strong{color:var(--text-2);font-weight:650}
    .status-chip .mini-dot{width:6px;height:6px;border-radius:50%;background:var(--cyan)}

    .content{max-width:1600px;margin:0 auto;padding:28px}
    .view{display:none}
    .view.active{display:block;animation:view-in .2s ease-out}
    @keyframes view-in{from{opacity:.25;transform:translateY(4px)}to{opacity:1;transform:none}}
    .mission-grid{display:grid;grid-template-columns:minmax(0,1fr) 340px;gap:20px;align-items:start}
    .main-column{min-width:0;display:grid;gap:18px}
    .inspector{min-width:0;display:grid;gap:14px;position:sticky;top:88px}
    .surface{
      border:1px solid var(--line);border-radius:var(--radius);background:var(--surface);
      box-shadow:0 1px 0 rgba(255,255,255,.018);
    }
    .surface-pad{padding:20px}

    .composer{position:relative;overflow:hidden;padding:25px}
    .composer:before{
      content:"";position:absolute;inset:-1px auto auto 8%;width:62%;height:1px;
      background:linear-gradient(90deg,transparent,var(--blue),transparent);opacity:.8;
    }
    .eyebrow{
      display:flex;align-items:center;gap:8px;margin-bottom:8px;
      color:var(--blue-2);font-size:11px;font-weight:750;letter-spacing:.1em;text-transform:uppercase;
    }
    .eyebrow:before{content:"";width:18px;height:1px;background:currentColor}
    h1{margin:0;font-size:30px;line-height:1.18;letter-spacing:-.035em;font-weight:710}
    .lede{margin:7px 0 19px;color:var(--text-3);max-width:680px}
    .prompt-box{
      border:1px solid #303646;border-radius:14px;background:#0b0d12;
      transition:border-color .16s,box-shadow .16s;
    }
    .prompt-box:focus-within{border-color:#6d7cff;box-shadow:0 0 0 3px rgba(109,124,255,.11)}
    textarea{
      display:block;width:100%;min-height:112px;resize:vertical;border:0;outline:0;
      padding:16px 17px 10px;background:transparent;color:var(--text);
      line-height:1.55;
    }
    textarea::placeholder,input::placeholder{color:#555e70}
    .prompt-actions{
      min-height:55px;display:flex;align-items:center;gap:9px;padding:8px;
      border-top:1px solid #1d212b;
    }
    select,input{
      min-height:42px;border:1px solid var(--line);border-radius:10px;background:#11141b;
      color:var(--text-2);padding:0 12px;outline:0;
    }
    select:focus,input:focus{border-color:var(--blue)}
    .autonomy{width:206px}
    .spacer{flex:1}
    .key-hint{color:#50596b;font-size:10px;white-space:nowrap}
    kbd{padding:2px 5px;border:1px solid #333947;border-bottom-width:2px;border-radius:5px;color:#7d8699}
    .button{
      min-height:42px;display:inline-flex;align-items:center;justify-content:center;gap:8px;
      border:1px solid transparent;border-radius:10px;padding:0 14px;cursor:pointer;
      font-weight:680;white-space:nowrap;transition:transform .15s,filter .15s,background .15s,border-color .15s;
    }
    .button:hover{filter:brightness(1.08)}
    .button:active{transform:translateY(1px)}
    .button:disabled{opacity:.45;cursor:not-allowed;filter:none}
    .button svg{width:17px;height:17px;fill:none;stroke:currentColor;stroke-width:1.8}
    .button.primary{background:var(--blue);color:#fff;box-shadow:0 7px 20px rgba(109,124,255,.2)}
    .button.secondary{background:#171a23;border-color:#303644;color:var(--text-2)}
    .button.positive{background:var(--green);color:#07140e}
    .button.warning{background:var(--amber);color:#171005}
    .button.danger{background:#28171c;border-color:#633039;color:#ffacb0}
    .button.small{min-height:34px;padding:0 11px;font-size:11px}
    .icon-button{
      width:38px;height:38px;display:grid;place-items:center;border:1px solid var(--line);
      border-radius:10px;background:transparent;color:var(--text-3);cursor:pointer;
    }
    .icon-button:hover{background:var(--surface-2);color:var(--text)}
    .icon-button svg{width:17px;height:17px;fill:none;stroke:currentColor;stroke-width:1.8}

    .run-card{overflow:hidden}
    .section-head{
      min-height:65px;display:flex;align-items:center;justify-content:space-between;gap:16px;
      padding:14px 18px;border-bottom:1px solid var(--line);
    }
    .section-title{min-width:0}
    .section-title h2{margin:0;font-size:14px;letter-spacing:-.01em}
    .section-title p{margin:2px 0 0;color:var(--text-3);font-size:11px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
    .run-status{display:flex;align-items:center;gap:8px}
    .badge{
      min-height:24px;display:inline-flex;align-items:center;gap:6px;padding:0 8px;
      border:1px solid #364052;border-radius:20px;color:#aeb8ca;
      background:#151923;font-size:9px;font-weight:750;letter-spacing:.07em;text-transform:uppercase;
    }
    .badge:before{content:"";width:5px;height:5px;border-radius:50%;background:currentColor}
    .badge.success{color:var(--green);border-color:#28513e;background:#10241b}
    .badge.warning{color:var(--amber);border-color:#604b28;background:#2b2110}
    .badge.danger{color:var(--red);border-color:#62323a;background:#2a151a}
    .badge.active{color:var(--blue-2);border-color:#414b8b;background:#181d3b}
    .run-id{font:10px ui-monospace,SFMono-Regular,Consolas,monospace;color:#596275}
    .stage-track{
      display:grid;grid-template-columns:repeat(4,1fr);padding:18px 20px 19px;
      border-bottom:1px solid var(--line);background:#0d0f14;
    }
    .stage{
      position:relative;display:grid;grid-template-rows:24px auto;justify-items:start;gap:6px;
      color:#596275;font-size:11px;font-weight:650;
    }
    .stage:not(:last-child):after{
      content:"";position:absolute;height:1px;left:31px;right:10px;top:12px;background:#2b303c;
    }
    .stage-dot{
      position:relative;z-index:1;width:24px;height:24px;display:grid;place-items:center;
      border:1px solid #323846;border-radius:50%;background:#11141a;font-size:9px;
    }
    .stage.current{color:#cbd0ff}
    .stage.current .stage-dot{border-color:var(--blue);background:#202750;box-shadow:0 0 0 4px rgba(109,124,255,.08)}
    .stage.complete{color:var(--text-2)}
    .stage.complete .stage-dot{border-color:#2f7957;background:#123122;color:var(--green)}
    .stage.complete:not(:last-child):after{background:#2e6b50}
    .tasks{padding:7px}
    .outcome{
      display:flex;align-items:flex-start;gap:12px;margin:15px 18px 5px;padding:14px 15px;
      border:1px solid #2b674b;border-radius:12px;background:linear-gradient(145deg,#11271c,#0e1914);
    }
    .outcome.hidden{display:none}
    .outcome-icon{
      width:34px;height:34px;display:grid;place-items:center;flex:0 0 auto;border-radius:10px;
      background:#17452f;color:var(--green);
    }
    .outcome-icon svg{width:19px;height:19px;fill:none;stroke:currentColor;stroke-width:2}
    .outcome h3{margin:0;color:#adf2cc;font-size:13px}
    .outcome p{margin:3px 0 0;color:#82aa94;font-size:11px}
    .task{
      display:grid;grid-template-columns:34px minmax(0,1fr) auto;gap:11px;align-items:start;
      padding:13px 12px;border-radius:11px;border:1px solid transparent;
    }
    .task+.task{border-top-color:#20242e;border-radius:0}
    .task:hover{background:#13161d}
    .task-index{
      width:29px;height:29px;display:grid;place-items:center;border:1px solid #303644;
      border-radius:9px;background:#171a22;color:#7e8798;font:10px ui-monospace,monospace;
    }
    .task.done .task-index{border-color:#28543e;background:#11271c;color:var(--green)}
    .task.wait .task-index{border-color:#644f2a;background:#2b2112;color:var(--amber)}
    .task-main{min-width:0}
    .task-main strong{display:block;font-size:12px;font-weight:650}
    .task-main p{margin:3px 0 0;color:var(--text-3);font-size:11px;overflow-wrap:anywhere}
    .task-meta{display:flex;align-items:center;justify-content:flex-end;gap:6px;flex-wrap:wrap}
    .meta-chip{padding:3px 7px;border:1px solid #292f3b;border-radius:6px;color:#697286;font-size:9px}
    .empty{
      min-height:150px;display:grid;place-items:center;padding:25px;text-align:center;color:var(--text-3);
    }
    .empty strong{display:block;margin-bottom:3px;color:var(--text-2);font-size:12px}

    .activity{overflow:hidden}
    .activity-list{max-height:340px;overflow:auto;padding:7px 18px 14px}
    .activity-row{display:grid;grid-template-columns:14px 102px 1fr;gap:10px;padding:9px 0;position:relative}
    .activity-row:not(:last-child):after{content:"";position:absolute;left:5px;top:25px;bottom:-5px;width:1px;background:#262b36}
    .activity-marker{width:11px;height:11px;margin-top:4px;border:2px solid #424958;border-radius:50%;background:var(--surface)}
    .activity-row:first-child .activity-marker{border-color:var(--blue);background:#29306b}
    .activity-type{color:#7b8496;font:10px/1.8 ui-monospace,monospace;overflow:hidden;text-overflow:ellipsis}
    .activity-message{color:var(--text-2);font-size:11px;overflow-wrap:anywhere}
    .activity-count{color:var(--text-3)}

    .action-card{
      overflow:hidden;border-color:#654d25;background:linear-gradient(155deg,#211b10,#13130f);
      box-shadow:0 16px 45px rgba(0,0,0,.2);
    }
    .action-card.hidden{display:none}
    .action-top{display:flex;gap:12px;padding:17px 17px 12px}
    .action-icon{
      flex:0 0 34px;height:34px;display:grid;place-items:center;border-radius:10px;
      background:#3c2e13;color:var(--amber);
    }
    .action-icon svg{width:18px;height:18px;stroke:currentColor;fill:none;stroke-width:1.8}
    .action-top h3{margin:0;color:#ffe1a4;font-size:12px}
    .action-top p{margin:4px 0 0;color:#aa9977;font-size:11px;overflow-wrap:anywhere}
    .action-details{
      max-height:132px;overflow:auto;margin:0 17px 14px;padding:10px;border:1px solid #45371f;
      border-radius:9px;background:#12110d;color:#c7b992;
      font:10px/1.55 ui-monospace,monospace;overflow-wrap:anywhere;
    }
    .action-buttons{display:grid;grid-template-columns:1fr 1fr;gap:8px;padding:0 17px 17px}
    .inspector-card{padding:17px}
    .inspector-title{
      margin:0 0 13px;color:#7f889b;font-size:10px;font-weight:750;letter-spacing:.1em;text-transform:uppercase;
    }
    .progress-ring-row{display:flex;align-items:center;gap:15px;margin-bottom:15px}
    .ring{
      --value:0;width:66px;height:66px;display:grid;place-items:center;flex:0 0 auto;border-radius:50%;
      background:conic-gradient(var(--blue) calc(var(--value)*1%),#242935 0);
      position:relative;
    }
    .ring:after{content:"";position:absolute;inset:6px;border-radius:50%;background:var(--surface)}
    .ring strong{position:relative;z-index:1;font-size:14px}
    .progress-copy strong{display:block;font-size:13px}
    .progress-copy span{color:var(--text-3);font-size:11px}
    .stat-grid{display:grid;grid-template-columns:1fr 1fr;border-top:1px solid var(--line);border-left:1px solid var(--line)}
    .mini-stat{padding:11px;border-right:1px solid var(--line);border-bottom:1px solid var(--line)}
    .mini-stat span{display:block;color:var(--text-3);font-size:9px;text-transform:uppercase;letter-spacing:.06em}
    .mini-stat strong{display:block;margin-top:3px;font-size:14px;font-weight:650;overflow:hidden;text-overflow:ellipsis}
    .kernel-list{display:grid;gap:11px}
    .kernel-row{display:flex;align-items:center;justify-content:space-between;gap:10px}
    .kernel-row span{color:var(--text-3);font-size:11px}
    .kernel-row strong{color:var(--text-2);font-size:11px;font-weight:650;text-align:right}
    .economy-note{
      display:flex;gap:10px;margin-top:14px;padding:11px;border:1px solid #293044;
      border-radius:10px;background:#111622;color:#7f8aaa;font-size:10px;
    }
    .economy-note svg{width:17px;height:17px;flex:0 0 auto;stroke:var(--blue-2);fill:none;stroke-width:1.8}

    .page-head{display:flex;align-items:end;justify-content:space-between;gap:18px;margin-bottom:20px}
    .page-head h1{font-size:25px}
    .page-head p{margin:6px 0 0;color:var(--text-3)}
    .tool-grid{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(300px,.65fr);gap:18px}
    .search-row{display:flex;gap:9px}
    .search-row input{flex:1}
    .code-output{
      min-height:210px;max-height:480px;overflow:auto;margin-top:13px;padding:15px;
      border:1px solid #252a36;border-radius:11px;background:#0a0c10;
      color:#aeb7c8;font:11px/1.65 ui-monospace,SFMono-Regular,Consolas,monospace;
      white-space:pre-wrap;overflow-wrap:anywhere;
    }
    .feature-list{display:grid;gap:9px;margin:13px 0 17px}
    .feature-row{display:flex;gap:9px;color:var(--text-3);font-size:11px}
    .feature-check{
      width:17px;height:17px;display:grid;place-items:center;flex:0 0 auto;border-radius:50%;
      background:#11271d;color:var(--green);font-size:9px;
    }
    .notice{
      padding:11px;border:1px solid #35405d;border-radius:10px;background:#111725;
      color:#98a4c7;font-size:11px;margin-bottom:13px;
    }
    .candidate-list{display:grid;gap:10px}
    .candidate{
      padding:16px;border:1px solid var(--line);border-radius:13px;background:#0d0f14;
    }
    .candidate-head{display:flex;align-items:start;justify-content:space-between;gap:12px}
    .candidate h3{margin:0;font-size:13px}
    .candidate-id{margin-top:3px;color:#596275;font:9px ui-monospace,monospace}
    .candidate-kind{display:inline-block;margin:12px 0 6px;color:var(--blue-2);font-size:10px;font-weight:650}
    .candidate-copy{
      max-height:118px;overflow:auto;margin:0;padding:10px;border-radius:8px;background:#11141a;
      color:#8b94a6;font:10px/1.55 ui-monospace,monospace;white-space:pre-wrap;overflow-wrap:anywhere;
    }
    .candidate-actions{display:flex;gap:7px;margin-top:12px;flex-wrap:wrap}
    .guardrails{display:grid;gap:1px;border:1px solid var(--line);border-radius:12px;overflow:hidden}
    .guardrail{display:flex;gap:10px;padding:11px;background:#101319;color:#8992a4;font-size:11px}
    .guardrail:before{content:"✓";color:var(--green)}
    .arena-hero{display:grid;grid-template-columns:180px 1fr;gap:22px;align-items:center}
    .score-box{
      aspect-ratio:1;display:grid;place-items:center;border:1px solid #343b50;border-radius:22px;
      background:radial-gradient(circle,rgba(109,124,255,.12),transparent 66%),#0d0f15;
    }
    .score-box span{display:block;text-align:center;color:var(--text-3);font-size:9px;text-transform:uppercase;letter-spacing:.1em}
    .score-box strong{display:block;text-align:center;font-size:40px;line-height:1.1;letter-spacing:-.05em}
    .category-list{display:grid;gap:14px}
    .category-row{display:grid;grid-template-columns:120px minmax(80px,1fr) 45px;gap:10px;align-items:center}
    .category-row span{color:var(--text-2);font-size:11px}
    .meter{height:7px;border-radius:10px;background:#242936;overflow:hidden}
    .meter i{display:block;width:0;height:100%;border-radius:inherit;background:linear-gradient(90deg,var(--blue),var(--cyan));transition:width .45s ease}
    .category-row strong{text-align:right;font-size:10px;color:var(--text-3)}

    .toast-stack{position:fixed;right:20px;bottom:20px;z-index:100;display:grid;gap:8px;pointer-events:none}
    .toast{
      min-width:250px;max-width:380px;padding:11px 13px;border:1px solid #3a4150;border-radius:11px;
      background:#171a22;color:var(--text-2);box-shadow:var(--shadow);font-size:11px;
      animation:toast-in .22s ease-out;
    }
    .toast.error{border-color:#63333c;color:#ffb1b5}
    .toast.success{border-color:#2d6047;color:#a0f0c6}
    @keyframes toast-in{from{opacity:0;transform:translateY(7px)}to{opacity:1;transform:none}}

    @media(max-width:1180px){
      .app{grid-template-columns:82px minmax(0,1fr)}
      .rail{padding-left:12px;padding-right:12px}
      .brand{justify-content:center;padding-left:0;padding-right:0}.brand-copy,.nav-label,.nav-button span:not(.nav-count),.rail-label,.system-tile,.rail-links{display:none}
      .nav-button{justify-content:center;padding:0}.nav-button.active:before{left:-12px}
      .nav-count{position:absolute;right:5px;top:2px;min-width:15px;height:15px;padding:0;font-size:8px}
    }
    @media(max-width:980px){
      .mission-grid,.tool-grid{grid-template-columns:1fr}
      .inspector{position:static;grid-template-columns:1fr 1fr}
      .action-card{grid-column:1/-1}
      .top-status .status-chip:first-child{display:none}
    }
    @media(max-width:720px){
      .app{display:block}
      .rail{
        position:fixed;inset:auto 0 0;height:68px;padding:8px 10px;display:block;
        border:1px solid var(--line);border-width:1px 0 0;background:rgba(11,12,17,.96);
      }
      .brand,.rail-bottom,.nav-label{display:none}
      .nav{grid-template-columns:repeat(4,1fr);height:100%;gap:4px}
      .nav-button{min-height:50px;display:grid;place-items:center;gap:0;padding:3px;font-size:9px}
      .nav-button span:not(.nav-count){display:block}
      .nav-button svg{width:18px;height:18px}
      .nav-button.active:before{left:25%;right:25%;top:-8px;width:auto;height:3px;border-radius:0 0 4px 4px}
      .topbar{height:58px;padding:0 15px}
      .top-status .status-chip{display:none}
      .content{padding:16px 13px 92px}
      .inspector{grid-row:1}
      .main-column{grid-row:2}
      .inspector .inspector-card{display:none}
      .composer{padding:18px}
      h1{font-size:25px}
      .prompt-actions{flex-wrap:wrap}
      .autonomy{width:100%;order:1}
      .spacer,.key-hint{display:none}
      .prompt-actions .button{flex:1;order:2}
      .inspector{grid-template-columns:1fr}
      .action-card{grid-column:auto;order:-1}
      .stage-track{padding:15px 12px}
      .stage{display:grid;justify-items:center;gap:5px;font-size:9px;text-align:center}
      .stage:not(:last-child):after{left:60%;right:-40%;top:12px}
      .task{grid-template-columns:31px minmax(0,1fr)}
      .task-meta{grid-column:2;justify-content:flex-start}
      .activity-row{grid-template-columns:14px 84px 1fr}
      .page-head{align-items:start;flex-direction:column}
      .page-head .button{width:100%}
      .search-row{flex-direction:column}
      .arena-hero{grid-template-columns:1fr}
      .score-box{width:150px;margin:auto}
      .category-row{grid-template-columns:90px 1fr 40px}
    }
    @media(prefers-reduced-motion:reduce){
      *,*:before,*:after{scroll-behavior:auto!important;animation:none!important;transition:none!important}
    }
  </style>
</head>
<body>
<div class="app">
  <aside class="rail" aria-label="Ana navigasyon">
    <div class="brand">
      <div class="brand-mark" aria-hidden="true">A</div>
      <div class="brand-copy"><div class="brand-name">Prometheus</div><div class="brand-version">Forge v0.8.0</div></div>
    </div>
    <div class="nav-label">Workspace</div>
    <nav class="nav" role="tablist" aria-label="Prometheus bölümleri">
      <button class="nav-button active" data-tab="mission" role="tab" aria-selected="true">
        <svg viewBox="0 0 24 24"><path d="M5 12h14M12 5l7 7-7 7"/></svg><span>Görev</span><span class="nav-count" id="approvalCount">0</span>
      </button>
      <button class="nav-button" data-tab="memory" role="tab" aria-selected="false">
        <svg viewBox="0 0 24 24"><path d="M4 6.5C4 5.7 4.7 5 5.5 5H9a3 3 0 0 1 3 3v11a3 3 0 0 0-3-3H4zM20 6.5c0-.8-.7-1.5-1.5-1.5H15a3 3 0 0 0-3 3v11a3 3 0 0 1 3-3h5z"/></svg><span>Bellek</span>
      </button>
      <button class="nav-button" data-tab="forge" role="tab" aria-selected="false">
        <svg viewBox="0 0 24 24"><path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M18.4 5.6l-2.1 2.1M7.7 16.3l-2.1 2.1"/><circle cx="12" cy="12" r="4"/></svg><span>Forge</span>
      </button>
      <button class="nav-button" data-tab="arena" role="tab" aria-selected="false">
        <svg viewBox="0 0 24 24"><path d="M4 19V9M10 19V5M16 19v-7M22 19H2"/></svg><span>Arena</span>
      </button>
    </nav>
    <div class="rail-bottom">
      <div class="rail-label">Runtime</div>
      <div class="system-tile">
        <div class="system-line"><span class="pulse" id="healthPulse"></span><span id="health">Bağlanıyor…</span></div>
        <div class="system-detail">yerel supervisor</div>
      </div>
      <div class="rail-links"><a class="rail-link" href="/command">Klasik</a><a class="rail-link" href="/docs">API</a></div>
    </div>
  </aside>

  <div class="workspace">
    <header class="topbar">
      <div class="crumb"><strong>Prometheus</strong><span class="crumb-divider">/</span><span id="crumbName">Canlı Test</span></div>
      <div class="top-status">
        <div class="status-chip"><span class="mini-dot"></span><span>Router</span><strong id="topRouter">—</strong></div>
        <div class="status-chip"><span>Yerel model</span><strong>Qwen3</strong></div>
      </div>
    </header>

    <main class="content">
      <section id="mission" class="view active" role="tabpanel">
        <div class="mission-grid">
          <div class="main-column">
            <section class="surface composer">
              <div class="eyebrow">Yeni görev</div>
              <h1>Prometheus ne üretsin?</h1>
              <p class="lede">Hedefi söyle. Prometheus işi böler, doğru bağlamı çağırır, üretir ve kanıtla doğrular.</p>
              <div class="prompt-box">
                <textarea id="goal" aria-label="Görev hedefi" placeholder="Örn. Workspace içinde sade, profesyonel ve test edilmiş bir hesap makinesi uygulaması oluştur."></textarea>
                <div class="prompt-actions">
                  <select id="autonomy" class="autonomy" aria-label="Otonomi seviyesi">
                    <option value="task">Önemli işlemlerde sor</option>
                    <option value="locked">Her yazmada sor</option>
                    <option value="trusted">Güvenli görevde otonom</option>
                  </select>
                  <span class="spacer"></span>
                  <span class="key-hint"><kbd>Ctrl</kbd> + <kbd>Enter</kbd></span>
                  <button class="button primary" id="startMission">
                    <svg viewBox="0 0 24 24"><path d="m5 4 15 8-15 8 3-8z"/></svg>Çalıştır
                  </button>
                </div>
              </div>
            </section>

            <section class="surface run-card">
              <div class="section-head">
                <div class="section-title"><h2 id="runTitle">Aktif çalışma</h2><p id="runSubtitle">Son görev otomatik olarak burada açılır.</p></div>
                <div class="run-status"><span class="run-id" id="runId">—</span><span class="badge" id="missionStatus">hazır</span>
                  <button class="icon-button" id="refreshMission" aria-label="Görevi yenile" title="Yenile">
                    <svg viewBox="0 0 24 24"><path d="M20 7v5h-5M4 17v-5h5M6.1 8a7 7 0 0 1 11.5-2L20 8M4 16l2.4 2a7 7 0 0 0 11.5-2"/></svg>
                  </button>
                </div>
              </div>
              <div class="stage-track" id="stageTrack" aria-label="Görev aşamaları">
                <div class="stage" data-stage="0"><span class="stage-dot">1</span><span>Planla</span></div>
                <div class="stage" data-stage="1"><span class="stage-dot">2</span><span>Bağlam</span></div>
                <div class="stage" data-stage="2"><span class="stage-dot">3</span><span>Üret</span></div>
                <div class="stage" data-stage="3"><span class="stage-dot">4</span><span>Doğrula</span></div>
              </div>
              <div class="outcome hidden" id="outcomeBanner" role="status">
                <div class="outcome-icon"><svg viewBox="0 0 24 24"><path d="m5 12 4 4L19 6"/></svg></div>
                <div><h3 id="outcomeTitle">Görev tamamlandı</h3><p id="outcomeText">Tüm alt görevler doğrulandı.</p></div>
              </div>
              <div class="tasks" id="taskList">
                <div class="empty"><div><strong>Henüz aktif görev yok</strong>Yukarıdan bir hedef vererek başlayın.</div></div>
              </div>
            </section>

            <section class="surface activity">
              <div class="section-head">
                <div class="section-title"><h2>Çalışma günlüğü</h2><p>Sistem adımları anlaşılır biçimde özetlenir.</p></div>
                <span class="badge" id="eventCount">0 olay</span>
              </div>
              <div class="activity-list" id="timeline">
                <div class="empty"><div><strong>Günlük hazır</strong>Çalışma başladığında doğrulanabilir olaylar burada görünür.</div></div>
              </div>
            </section>
          </div>

          <aside class="inspector" aria-label="Görev denetçisi">
            <section class="surface action-card hidden" id="approvalPanel">
              <div class="action-top">
                <div class="action-icon"><svg viewBox="0 0 24 24"><path d="M12 3 2.5 20h19zM12 9v5M12 17.5v.5"/></svg></div>
                <div><h3 id="approvalTitle">Kararın gerekiyor</h3><p id="approvalDescription">—</p></div>
              </div>
              <div class="action-details" id="approvalDetails">—</div>
              <div class="action-buttons" id="approvalButtons"></div>
            </section>

            <section class="surface inspector-card">
              <h2 class="inspector-title">Çalışma durumu</h2>
              <div class="progress-ring-row">
                <div class="ring" id="missionRing"><strong id="missionPercent">0%</strong></div>
                <div class="progress-copy"><strong id="missionProgress">0 / 0 görev</strong><span id="missionStateCopy">Başlamaya hazır</span></div>
              </div>
              <div class="stat-grid">
                <div class="mini-stat"><span>Bölüm</span><strong id="mEpisodes">—</strong></div>
                <div class="mini-stat"><span>Yönlendirme</span><strong id="mOrient">—</strong></div>
                <div class="mini-stat"><span>Strateji</span><strong id="mStrategies">—</strong></div>
                <div class="mini-stat"><span>Forge adayı</span><strong id="mCandidates">—</strong></div>
              </div>
            </section>

            <section class="surface inspector-card">
              <h2 class="inspector-title">Experience Kernel</h2>
              <div class="kernel-list">
                <div class="kernel-row"><span>Router</span><strong id="mRouter">—</strong></div>
                <div class="kernel-row"><span>Embedding</span><strong id="embeddingShort">—</strong></div>
                <div class="kernel-row"><span>Otonomi</span><strong id="autonomyState">önemli işlemde sor</strong></div>
              </div>
              <div class="economy-note">
                <svg viewBox="0 0 24 24"><path d="M13 2 5 13h6l-1 9 8-12h-6z"/></svg>
                <span>PEEK yalnızca işe yarayan bağlamı çağırır; gereksiz proje geçmişi modele taşınmaz.</span>
              </div>
            </section>
          </aside>
        </div>
      </section>

      <section id="memory" class="view" role="tabpanel">
        <div class="page-head">
          <div><div class="eyebrow">Experience Kernel</div><h1>Bellek & RAG</h1><p>Az bağlamla doğru kararı bulmak için proje belleğini sorgula.</p></div>
        </div>
        <div class="tool-grid">
          <section class="surface surface-pad">
            <div class="section-title"><h2>PEEK / TLB hatırlama</h2><p>Sorguya en yakın yönlendirme ve doğrulanmış stratejiler.</p></div>
            <div class="search-row" style="margin-top:17px">
              <input id="recallQuery" aria-label="Bellek sorgusu" placeholder="Örn. Python hesap makinesi test hatasını düzelt">
              <button class="button primary" id="recallBtn">Belleği tara</button>
            </div>
            <pre class="code-output" id="recallOutput">Henüz sorgu yok.</pre>
          </section>
          <section class="surface surface-pad">
            <div class="section-title"><h2>Yerel hibrit dizin</h2><p>Kaynak kodu dışarı göndermeden lexical + semantic arama.</p></div>
            <div class="feature-list">
              <div class="feature-row"><span class="feature-check">✓</span><span>SQLite tabanlı lexical dizin</span></div>
              <div class="feature-row"><span class="feature-check">✓</span><span>Yerel Qwen3 Embedding</span></div>
              <div class="feature-row"><span class="feature-check">✓</span><span>Sabit karakter bütçesi</span></div>
            </div>
            <div class="notice" id="embeddingInfo">Embedding durumu yükleniyor…</div>
            <button class="button secondary" id="indexBtn">Workspace’i yeniden dizinle</button>
            <pre class="code-output" id="indexOutput" style="min-height:110px">—</pre>
          </section>
        </div>
      </section>

      <section id="forge" class="view" role="tabpanel">
        <div class="page-head">
          <div><div class="eyebrow">Denetimli gelişim</div><h1>Prometheus Forge</h1><p>İyileştirme önerilir, Arena’da ölçülür, yalnızca açık onayla terfi eder.</p></div>
          <button class="button primary" id="suggestBtn">Yeni aday üret</button>
        </div>
        <div class="tool-grid">
          <section class="surface surface-pad">
            <div class="section-title" style="margin-bottom:15px"><h2>İyileştirme adayları</h2><p>Aktif ve değerlendirme bekleyen öneriler.</p></div>
            <div class="candidate-list" id="candidateCards"><div class="empty"><div><strong>Adaylar yükleniyor</strong>Forge kayıtları okunuyor.</div></div></div>
          </section>
          <section class="surface surface-pad">
            <div class="section-title" style="margin-bottom:15px"><h2>Güvenlik sınırı</h2><p>Kendi kendini değiştirme kontrollü ve geri alınabilir.</p></div>
            <div class="guardrails">
              <div class="guardrail">Gizli testler aday üreticisine verilmez.</div>
              <div class="guardrail">API anahtarları ve .env içeriği laboratuvara girmez.</div>
              <div class="guardrail">Kaynak yamaları yalnızca gölge kopyada ayrıştırılır.</div>
              <div class="guardrail">Kaynak yaması otomatik çalıştırılmaz veya terfi etmez.</div>
              <div class="guardrail">Strateji terfisi için “PROMETHEUS ONAYLIYORUM” gerekir.</div>
              <div class="guardrail">Her terfi sürümlüdür ve geri alınabilir.</div>
            </div>
          </section>
        </div>
      </section>

      <section id="arena" class="view" role="tabpanel">
        <div class="page-head">
          <div><div class="eyebrow">Kalite kapısı</div><h1>40-vaka Improvement Arena</h1><p>Patch, retrieval, routing ve adversarial güvenlik tek koşuda ölçülür.</p></div>
          <button class="button primary" id="benchmarkBtn">Benchmark çalıştır</button>
        </div>
        <section class="surface surface-pad">
          <div class="arena-hero">
            <div class="score-box"><div><span>Kalite skoru</span><strong id="benchScore">—</strong></div></div>
            <div>
              <div class="section-title"><h2>Kategori sonuçları</h2><p>Görünür, gizli ve saldırgan vaka toplamları.</p></div>
              <div class="category-list" id="benchCategories" style="margin-top:18px">
                <div class="empty" style="min-height:105px"><div><strong>Sonuç bekleniyor</strong>Benchmark henüz çalıştırılmadı.</div></div>
              </div>
            </div>
          </div>
          <pre class="code-output" id="benchOutput">Henüz çalıştırılmadı.</pre>
        </section>
      </section>
    </main>
  </div>
</div>
<div class="toast-stack" id="toastStack" aria-live="polite"></div>

<script>
const $=id=>document.getElementById(id);
const ACTIVE_COMMAND_KEY="prometheus.activeCommandId";
const LEGACY_COMMAND_KEY="adam.activeCommandId";
let commandId=localStorage.getItem(ACTIVE_COMMAND_KEY)||localStorage.getItem(LEGACY_COMMAND_KEY);
if(commandId&&!localStorage.getItem(ACTIVE_COMMAND_KEY)){localStorage.setItem(ACTIVE_COMMAND_KEY,commandId)}
let pollTimer=null,lastStatus=null,statusSnapshot=null;
const esc=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const TERMINAL=new Set(["completed","failed","blocked","cancelled"]);
const LABELS={
  completed:"tamamlandı",running:"çalışıyor",pending:"bekliyor",planned:"planlandı",
  awaiting_approval:"onay bekliyor",rework_required:"yeniden çalışma",failed:"başarısız",
  blocked:"engellendi",dependency_wait:"önceki adımı bekliyor",
  cancelled:"iptal",ready:"hazır",created:"oluşturuldu"
};
const EVENT_LABELS={
  task_evidence_review_accepted:"Doğrulama geçti",
  task_evidence_review_rejected:"Doğrulama geri çevirdi",
  task_evidence_incomplete:"Kanıt eksik",
  task_started:"Görev başladı",
  task_completed:"Görev tamamlandı",
  command_completed:"Tüm çalışma tamamlandı",
  task_approval_required:"Onay gerekiyor",
  approval_transaction_started:"Onay uygulanıyor",
  approval_tool_checkpointed:"İşlem tamamlandı",
  approval_tool_application_failed:"İşlem uygulanamadı",
  scoped_tool_auto_applied:"Güvenli işlem tamamlandı",
  viewer_context_prepared:"Proje bağlamı hazır",
  local_model_first_attempt:"Yerel model denemesi",
  focused_generation_revision_advanced:"Üretim altyapısı hazır",
  focused_step_failed:"Kalite kontrolü geçmedi",
  resume_ignored_no_state_change:"Tekrar önlendi",
  background_crashed:"Arka plan çalışması durdu"
};

async function api(path,opts={}){
  const res=await fetch(path,{headers:{"Content-Type":"application/json"},...opts});
  const body=await res.json().catch(()=>({detail:res.statusText}));
  if(!res.ok)throw new Error(typeof body.detail==="string"?body.detail:JSON.stringify(body.detail||body));
  return body;
}
function toast(message,type=""){
  const node=document.createElement("div");
  node.className=`toast ${type}`;node.textContent=message;$("toastStack").appendChild(node);
  setTimeout(()=>node.remove(),4200);
}
function toastError(err){console.error(err);toast("Hata: "+err.message,"error")}
function statusLabel(value){return LABELS[value]||String(value||"hazır").replaceAll("_"," ")}
function badgeClass(value){
  if(["completed","promoted","passed"].includes(value))return"success";
  if(["awaiting_approval","pending","proposed","rework_required"].includes(value))return"warning";
  if(["failed","blocked","cancelled","rejected"].includes(value))return"danger";
  if(["running","evaluating"].includes(value))return"active";
  return"";
}
function openTab(tabId){
  document.querySelectorAll(".nav-button[data-tab]").forEach(btn=>{
    const active=btn.dataset.tab===tabId;btn.classList.toggle("active",active);btn.setAttribute("aria-selected",String(active));
  });
  document.querySelectorAll(".view").forEach(view=>view.classList.toggle("active",view.id===tabId));
  const names={mission:"Canlı Test",memory:"Bellek & RAG",forge:"Prometheus Forge",arena:"Improvement Arena"};
  $("crumbName").textContent=names[tabId]||"Workspace";
  window.scrollTo({top:0,behavior:"smooth"});
}
document.querySelectorAll(".nav-button[data-tab]").forEach(btn=>btn.addEventListener("click",()=>openTab(btn.dataset.tab)));

async function loadStatus(){
  try{
    const s=await api("/v1/improvement/status");statusSnapshot=s;
    $("mEpisodes").textContent=s.episodes;$("mOrient").textContent=s.orientation_entries;
    $("mStrategies").textContent=s.strategies;$("mCandidates").textContent=s.candidates;
    $("mRouter").textContent=String(s.router_mode||"—").toUpperCase();$("topRouter").textContent=String(s.router_mode||"—").toUpperCase();
    $("embeddingShort").textContent=s.embedding_enabled?"Qwen3 · yerel":"lexical fallback";
    $("health").textContent="Sistem hazır";$("healthPulse").classList.add("online");
    $("embeddingInfo").textContent=s.embedding_enabled
      ?`Etkin · ${s.embedding_model} · ${s.orientation_budget_chars} karakter bütçesi`
      :"Embedding kapalı; lexical fallback etkin.";
    loadCandidates();
  }catch(e){
    $("health").textContent="Bağlantı hatası";$("healthPulse").classList.remove("online");toastError(e);
  }
}
function normalizedEvents(events){
  const recent=(events||[]).slice(-80).reverse(),rows=[];
  for(const event of recent){
    const key=`${event.type}|${event.task_id||""}|${event.message||""}`;
    if(rows.length&&rows[rows.length-1].key===key){rows[rows.length-1].count++;continue}
    rows.push({...event,key,count:1});
  }
  return rows.slice(0,35);
}
function presentEvent(event){
  const task=event.task_id||"Görev";
  const messages={
    task_evidence_review_accepted:`${task} çıktısı bağımsız doğrulama kontrolünden geçti.`,
    task_evidence_review_rejected:`${task} çıktısı doğrulama koşullarını karşılamadı ve düzeltmeye gönderildi.`,
    task_evidence_incomplete:`${task} için tamamlanma kanıtı henüz yeterli değil.`,
    task_started:`${task} üzerinde çalışma başladı.`,
    task_completed:`${task} başarıyla tamamlandı.`,
    command_completed:"İstenen çalışmanın bütün adımları tamamlandı ve doğrulandı.",
    task_approval_required:`${task} için devam etmeden önce kararınız gerekiyor.`,
    approval_transaction_started:"Onayladığınız güvenli işlem uygulanıyor.",
    approval_tool_checkpointed:"Onaylanan güvenli işlem başarıyla tamamlandı.",
    approval_tool_application_failed:"Onaylanan işlem uygulanamadı; güvenli yeniden deneme gerekiyor.",
    scoped_tool_auto_applied:"Otonomi kapsamındaki güvenli işlem başarıyla tamamlandı.",
    viewer_context_prepared:"Bu görev için gerekli proje bilgileri hazırlandı.",
    local_model_first_attempt:"Maliyeti düşük tutmak için ilk deneme yerel modele verildi.",
    focused_generation_revision_advanced:"Güvenli ve kesilmeye dayanıklı dosya üretim yöntemi hazırlandı.",
    focused_step_failed:"Bu deneme kalite kontrolünden geçmedi; aynı hatalı yanıt tekrar kullanılmayacak.",
    resume_ignored_no_state_change:"Yeni bir değişiklik olmadığı için aynı başarısız işlem yeniden çalıştırılmadı.",
    background_crashed:"Arka plan çalışması beklenmedik biçimde durdu."
  };
  const fallback=String(event.message||"Sistem durumu güncellendi.")
    .replace(/Independent Evidence Reviewer tarafından kabul edildi\.?/gi,"bağımsız doğrulama kontrolünden geçti.");
  return{label:EVENT_LABELS[event.type]||"Sistem güncellemesi",message:messages[event.type]||fallback};
}
function renderStages(command,tasks,done){
  const events=command.events||[],eventText=events.map(e=>`${e.type} ${e.message}`).join(" ").toLowerCase();
  let current=0;
  if(tasks.length)current=1;
  if(eventText.match(/viewer|context|orientation|recall|retriev|bağlam/))current=2;
  if(tasks.some(t=>["running","completed","awaiting_approval","rework_required"].includes(t.status)))current=2;
  if(eventText.match(/verif|test|evidence|doğrula/)||done>0)current=3;
  if(command.status==="completed")current=4;
  document.querySelectorAll(".stage").forEach((stage,index)=>{
    stage.classList.toggle("complete",index<current);
    stage.classList.toggle("current",index===current&&current<4);
    stage.querySelector(".stage-dot").textContent=index<current?"✓":String(index+1);
  });
}
function taskCopy(task){
  return task.description||task.goal||task.title||task.command||task.last_answer||"Supervisor görevi";
}
function approvalSummary(task){
  const description=task.approval_description||task.last_approval_message||"Dosya veya terminal işlemi";
  const preview=task.approval_preview||{};
  if(Array.isArray(preview.logical_command)&&preview.logical_command.length){
    return `${description}\n\nÇalıştırılacak komut: ${preview.logical_command.join(" ")}`;
  }
  if(preview.path){
    return `${description}\n\nHedef: ${preview.path}${preview.operation?` · İşlem: ${preview.operation}`:""}`;
  }
  return description;
}
function friendlyFailure(task){
  const raw=String(task.blocked_reason||task.last_answer||task.recovery_reason||"Görev tamamlanamadı.");
  const normalized=raw.toLocaleLowerCase("tr");
  if(normalized.includes("hiçbir model rotasından cevap alınamadı")){
    if(normalized.includes("token sınırında kesildi")){
      return "Yerel modelin cevabı yarıda kesildi; diğer ücretsiz modeller de bu denemede kalite kontrolünden geçemedi. Yerel modelin çıktı alanı genişletildi ve yeniden deneme artık engellenmiyor.";
    }
    return "Ücretsiz model rotaları bu denemede geçerli bir çıktı üretemedi. Aynı cevabı körlemesine tekrarlamak yerine düzeltilmiş akışla yeniden denenebilir.";
  }
  if(normalized.includes("resume_ignored_no_state_change")){
    return "Sistem aynı başarısız işlemi tekrar çalıştırmayarak bir döngüyü durdurdu. Yeni yeniden deneme akışı artık farklı bir model bütçesi ve hata geri bildirimi kullanacak.";
  }
  return raw.length>480?raw.slice(0,477)+"…":raw;
}
function renderTasks(tasks){
  if(!tasks.length){
    $("taskList").innerHTML='<div class="empty"><div><strong>Plan hazırlanıyor</strong>Alt görevler birazdan burada görünecek.</div></div>';return;
  }
  $("taskList").innerHTML=tasks.map((task,index)=>{
    const state=task.approval_state==="pending"
      ?"awaiting_approval"
      :task.status==="blocked"&&(task.dependencies||[]).length
        ?"dependency_wait"
        :task.status;
    const cls=task.status==="completed"?"done":state==="awaiting_approval"||state==="rework_required"?"wait":"";
    const route=task.route||task.model||task.assigned_model||task.provider;
    return `<article class="task ${cls}">
      <div class="task-index">${task.status==="completed"?"✓":String(index+1).padStart(2,"0")}</div>
      <div class="task-main"><strong>${esc(task.id||`Görev ${index+1}`)}</strong><p>${esc(taskCopy(task))}</p></div>
      <div class="task-meta">${route?`<span class="meta-chip">${esc(route)}</span>`:""}<span class="badge ${badgeClass(state)}">${esc(statusLabel(state))}</span></div>
    </article>`;
  }).join("");
}
function renderApproval(tasks){
  const pending=tasks.find(t=>t.approval_state==="pending"&&t.approval_id);
  const rework=tasks.find(t=>t.status==="rework_required");
  const count=tasks.filter(t=>(t.approval_state==="pending"&&t.approval_id)||t.status==="rework_required").length;
  $("approvalCount").textContent=count;$("approvalCount").classList.toggle("show",count>0);
  const panel=$("approvalPanel");
  if(!pending&&!rework){panel.classList.add("hidden");return}
  panel.classList.remove("hidden");
  if(pending){
    $("approvalTitle").textContent=`${pending.id} için karar gerekiyor`;
    $("approvalDescription").textContent="Prometheus bu önemli işlemi siz onaylamadan yürütmeyecek.";
    $("approvalDetails").textContent=approvalSummary(pending);
    $("approvalButtons").innerHTML=`<button class="button danger" onclick="decide('${esc(pending.id)}',false)">Reddet</button><button class="button warning" onclick="decide('${esc(pending.id)}',true)">Onayla</button>`;
  }else{
    $("approvalTitle").textContent=`${rework.id} yeniden çalışmalı`;
    $("approvalDescription").textContent="Doğrulama kapısı görevi geri çevirdi.";
    $("approvalDetails").textContent=friendlyFailure(rework);
    $("approvalButtons").innerHTML=`<button class="button warning" style="grid-column:1/-1" onclick="retryTask('${esc(rework.id)}')">Düzeltilmiş akışla yeniden dene</button>`;
  }
}
function renderCommand(command){
  lastStatus=command;
  const tasks=command.tasks||[],done=tasks.filter(t=>t.status==="completed").length;
  const percent=tasks.length?Math.round(100*done/tasks.length):0;
  const hasPending=tasks.some(task=>task.approval_state==="pending"&&task.approval_id);
  const hasRework=tasks.some(task=>task.status==="rework_required");
  const state=hasPending?"awaiting_approval":hasRework?"rework_required":command.status||"ready";
  $("missionStatus").textContent=statusLabel(state);$("missionStatus").className=`badge ${badgeClass(state)}`;
  $("missionProgress").textContent=`${done} / ${tasks.length} görev`;
  $("missionPercent").textContent=`${percent}%`;$("missionRing").style.setProperty("--value",percent);
  $("missionStateCopy").textContent=state==="completed"?"Tüm kanıtlar doğrulandı":state==="awaiting_approval"?"Kararınız bekleniyor":statusLabel(state);
  $("runTitle").textContent=command.goal||command.title||"Aktif çalışma";
  $("runSubtitle").textContent=tasks.length?`${tasks.length} alt görev · ${done} tamamlandı`:"Plan hazırlanıyor";
  $("runId").textContent=command.id?`#${String(command.id).slice(0,8)}`:"—";
  $("autonomyState").textContent=String(command.autonomy_mode||$("autonomy").value).replace("task","önemli işlemde sor").replace("locked","her yazmada sor").replace("trusted","güvenli görevde otonom");
  const outcome=$("outcomeBanner");
  if(command.status==="completed"){
    outcome.classList.remove("hidden");
    $("outcomeTitle").textContent="Görev tamamlandı";
    $("outcomeText").textContent=`${done} alt görevin tamamı bağımsız kontrolden geçti. İstenen çıktı kullanıma hazır.`;
  }else{
    outcome.classList.add("hidden");
  }
  renderStages(command,tasks,done);renderTasks(tasks);renderApproval(tasks);
  const events=normalizedEvents(command.events);
  $("eventCount").textContent=`${(command.events||[]).length} kayıt`;
  $("timeline").innerHTML=events.length?events.map(event=>{
    const shown=presentEvent(event);
    return `<div class="activity-row">
      <span class="activity-marker"></span>
      <span class="activity-type">${esc(shown.label)}${event.task_id?`<br>· ${esc(event.task_id)}`:""}</span>
      <span class="activity-message">${esc(shown.message)}${event.count>1?` <span class="activity-count">×${event.count}</span>`:""}</span>
    </div>`;
  }).join(""):'<div class="empty"><div><strong>Planlanıyor</strong>İlk çalışma kaydı bekleniyor.</div></div>';
  if(TERMINAL.has(command.status)&&pollTimer){clearInterval(pollTimer);pollTimer=null}
}
async function refreshMission(){
  if(!commandId)return;
  try{renderCommand(await api(`/v1/supervisor/commands/${commandId}`))}catch(e){toastError(e)}
}
async function decide(taskId,approve){
  const task=(lastStatus?.tasks||[]).find(x=>x.id===taskId);if(!task)return;
  try{
    const path=`/v1/supervisor/commands/${commandId}/tasks/${taskId}/${approve?"approve":"reject"}`;
    renderCommand(await api(path,{method:"POST",body:JSON.stringify({
      approval_id:task.approval_id,approval_version:task.approval_version,background:true
    })}));
    toast(approve?"İşlem onaylandı. Prometheus devam ediyor.":"İşlem reddedildi.","success");
    if(approve&&!pollTimer)pollTimer=setInterval(refreshMission,2500);
  }catch(e){toastError(e)}
}
async function retryTask(taskId){
  try{
    renderCommand(await api(`/v1/supervisor/commands/${commandId}/tasks/${taskId}/run?background=true`,{method:"POST"}));
    if(!pollTimer)pollTimer=setInterval(refreshMission,2500);toast("Görev yeniden başlatıldı.","success");
  }catch(e){toastError(e)}
}
async function startMission(){
  const goal=$("goal").value.trim();if(goal.length<3){toast("Önce kısa bir görev hedefi yazın.","error");return}
  $("startMission").disabled=true;
  try{
    const command=await api("/v1/supervisor/commands",{method:"POST",body:JSON.stringify({
      goal,autonomy_mode:$("autonomy").value,routing_mode:"auto",auto_start:true,background:true
    })});
    commandId=command.id;localStorage.setItem(ACTIVE_COMMAND_KEY,commandId);renderCommand(command);
    if(pollTimer)clearInterval(pollTimer);pollTimer=setInterval(refreshMission,2500);
    toast("Görev Prometheus’a teslim edildi.","success");
  }catch(e){toastError(e)}finally{$("startMission").disabled=false}
}
$("startMission").addEventListener("click",startMission);
$("goal").addEventListener("keydown",event=>{if((event.ctrlKey||event.metaKey)&&event.key==="Enter")startMission()});
$("refreshMission").addEventListener("click",refreshMission);

$("recallBtn").addEventListener("click",async()=>{
  const button=$("recallBtn");button.disabled=true;$("recallOutput").textContent="Bellek taranıyor…";
  try{
    const result=await api("/v1/improvement/recall",{method:"POST",body:JSON.stringify({query:$("recallQuery").value||"project architecture"})});
    $("recallOutput").textContent=result.text+"\n\n"+JSON.stringify({
      task_signature:result.task_signature,strategies:result.strategy_ids,orientation:result.orientation_ids,
      chars:result.chars,lexical_only:result.lexical_only
    },null,2);
  }catch(e){$("recallOutput").textContent=e.message;toastError(e)}finally{button.disabled=false}
});
$("recallQuery").addEventListener("keydown",event=>{if(event.key==="Enter")$("recallBtn").click()});
$("indexBtn").addEventListener("click",async()=>{
  const button=$("indexBtn");button.disabled=true;$("indexOutput").textContent="Yerel dizin hazırlanıyor; ilk çalıştırma birkaç dakika sürebilir…";
  try{
    const result=await api("/v1/improvement/index",{method:"POST"});
    $("indexOutput").textContent=JSON.stringify(result,null,2);await loadStatus();toast("Workspace dizini güncellendi.","success");
  }catch(e){$("indexOutput").textContent=e.message;toastError(e)}finally{button.disabled=false}
});
function candidatePayload(candidate){
  try{
    const data=typeof candidate.payload_json==="string"?JSON.parse(candidate.payload_json):candidate.payload_json;
    return JSON.stringify(data,null,2);
  }catch(_){return candidate.payload_json||"İçerik yok"}
}
async function loadCandidates(){
  try{
    const rows=await api("/v1/improvement/candidates");
    $("candidateCards").innerHTML=rows.length?rows.map(candidate=>`<article class="candidate">
      <div class="candidate-head"><div><h3>${esc(candidate.title)}</h3><div class="candidate-id">${esc(candidate.id)}</div></div>
      <span class="badge ${badgeClass(candidate.status)}">${esc(statusLabel(candidate.status))}</span></div>
      <span class="candidate-kind">${esc(candidate.kind)}</span>
      <pre class="candidate-copy">${esc(candidatePayload(candidate))}</pre>
      <div class="candidate-actions">
        ${candidate.status==="proposed"?`<button class="button secondary small" onclick="evaluateCandidate('${esc(candidate.id)}')">Arena’da değerlendir</button>`:""}
        ${candidate.status==="evaluated"?`<button class="button positive small" onclick="promoteCandidate('${esc(candidate.id)}')">Terfi et</button>`:""}
        ${candidate.status==="promoted"?`<button class="button danger small" onclick="rollbackCandidate('${esc(candidate.id)}')">Geri al</button>`:""}
      </div>
    </article>`).join(""):'<div class="empty"><div><strong>Henüz aday yok</strong>Prometheus’un doğrulanmış deneyimlerinden yeni bir öneri üretin.</div></div>';
  }catch(e){toastError(e)}
}
$("suggestBtn").addEventListener("click",async()=>{
  const button=$("suggestBtn");button.disabled=true;
  try{await api("/v1/improvement/candidates/suggest",{method:"POST"});await loadStatus();toast("Yeni iyileştirme adayı üretildi.","success")}
  catch(e){toastError(e)}finally{button.disabled=false}
});
async function evaluateCandidate(id){
  try{await api(`/v1/improvement/candidates/${id}/evaluate`,{method:"POST"});await loadCandidates();toast("Aday Arena’da değerlendirildi.","success")}catch(e){toastError(e)}
}
async function promoteCandidate(id){
  const confirmation=prompt("Terfi için tam olarak “PROMETHEUS ONAYLIYORUM” yazın:");if(!confirmation)return;
  try{await api(`/v1/improvement/candidates/${id}/promote`,{method:"POST",body:JSON.stringify({confirmation})});await loadStatus();toast("Aday güvenli biçimde terfi etti.","success")}catch(e){toastError(e)}
}
async function rollbackCandidate(id){
  if(!confirm("Bu etkin politikayı geri almak istiyor musunuz?"))return;
  try{await api(`/v1/improvement/candidates/${id}/rollback`,{method:"POST"});await loadStatus();toast("Politika geri alındı.","success")}catch(e){toastError(e)}
}
$("benchmarkBtn").addEventListener("click",async()=>{
  const button=$("benchmarkBtn");button.disabled=true;$("benchOutput").textContent="40 vaka çalıştırılıyor…";
  try{
    const result=await api("/v1/improvement/benchmark/run",{method:"POST",body:"{}"});
    $("benchScore").textContent=Number(result.score).toFixed(1);$("benchOutput").textContent=JSON.stringify(result,null,2);
    $("benchCategories").innerHTML=Object.entries(result.by_category||{}).map(([name,value])=>{
      const percent=value.total?100*value.passed/value.total:0;
      return `<div class="category-row"><span>${esc(name)}</span><div class="meter"><i style="width:${percent}%"></i></div><strong>${value.passed}/${value.total}</strong></div>`;
    }).join("")||'<div class="empty"><div><strong>Kategori yok</strong>Benchmark yanıtı ayrıntı içermedi.</div></div>';
    await loadStatus();toast("Arena koşusu tamamlandı.","success");
  }catch(e){$("benchOutput").textContent=e.message;toastError(e)}finally{button.disabled=false}
});
async function resumeLatestCommand(){
  try{
    const commands=await api("/v1/supervisor/commands");
    const substantive=commands.filter(command=>(command.tasks||[]).length||String(command.goal||"").trim().length>8)
      .sort((a,b)=>Date.parse(b.updated_at||b.created_at||0)-Date.parse(a.updated_at||a.created_at||0));
    const selected=commands.find(command=>command.id===commandId)||substantive[0]||commands[0];
    if(!selected)return;
    commandId=selected.id;localStorage.setItem(ACTIVE_COMMAND_KEY,commandId);await refreshMission();
    if(!TERMINAL.has(lastStatus?.status)){
      if(pollTimer)clearInterval(pollTimer);pollTimer=setInterval(refreshMission,2500);
    }
  }catch(e){toastError(e)}
}
loadStatus();
resumeLatestCommand();
</script>
</body>
</html>
"""
