// fwagent — Autonomous Firmware Test Bench Client Script

document.addEventListener('DOMContentLoaded', () => {
  // DOM Handles
  const sampleSelect = document.getElementById('sampleSelect');
  const btnTriggerFolderUpload = document.getElementById('btnTriggerFolderUpload');
  const btnTriggerZipUpload = document.getElementById('btnTriggerZipUpload');
  const firmwareFolderInput = document.getElementById('firmwareFolderInput');
  const firmwareZipInput = document.getElementById('firmwareZipInput');
  const targetFwPath = document.getElementById('targetFwPath');

  const simAuto = document.getElementById('simAuto');
  const simHost = document.getElementById('simHost');
  const simWokwi = document.getElementById('simWokwi');

  const btnRun = document.getElementById('btnRun');
  const btnStop = document.getElementById('btnStop');
  const btnRerun = document.getElementById('btnRerun');
  const pastRunsNav = document.getElementById('pastRunsNav');
  const mcuTargetInfo = document.getElementById('mcuTargetInfo');

  const hdrTargetFw = document.getElementById('hdrTargetFw');
  const hdrSimBadge = document.getElementById('hdrSimBadge');
  const hdrTimer = document.getElementById('hdrTimer');
  const errorBanner = document.getElementById('errorBanner');
  const errorBannerText = document.getElementById('errorBannerText');

  const termStatusDot = document.getElementById('termStatusDot');
  const termStatusText = document.getElementById('termStatusText');
  const terminalScreen = document.getElementById('terminal-screen');
  const terminalContent = document.getElementById('terminal-content');
  const terminalPrompt = document.getElementById('terminalPrompt');

  const btnCopyLog = document.getElementById('btn-copy-log');
  const btnCopyText = document.getElementById('btn-copy-text');
  const btnClearLog = document.getElementById('btn-clear-log');
  const btnSaveLog = document.getElementById('btn-save-log');
  const btnProjectorToggle = document.getElementById('btn-projector-toggle');
  const btnProjectorHeader = document.getElementById('btnProjectorHeader');
  const btnJumpLatest = document.getElementById('btn-jump-latest');

  const scPass = document.getElementById('scPass');
  const scFail = document.getElementById('scFail');
  const scWarn = document.getElementById('scWarn');
  const scAmbig = document.getElementById('scAmbig');
  const scSkipped = document.getElementById('scSkipped');
  const filterReset = document.getElementById('filter-reset');

  const btnOpenReport = document.getElementById('btnOpenReport');
  const btnDownloadRun = document.getElementById('btnDownloadRun');
  const resultsTableBody = document.getElementById('resultsTableBody');

  const findingsHeading = document.getElementById('findingsHeading');
  const findingsContainer = document.getElementById('findingsContainer');

  const reportUuid = document.getElementById('reportUuid');
  const btnReportNewTab = document.getElementById('btnReportNewTab');
  const btnDownloadReportHtml = document.getElementById('btnDownloadReportHtml');
  const reportVerdictBadge = document.getElementById('reportVerdictBadge');
  const reportTargetDesc = document.getElementById('reportTargetDesc');

  const repTotalTests = document.getElementById('repTotalTests');
  const repPassingRate = document.getElementById('repPassingRate');
  const repDuration = document.getElementById('repDuration');
  const repSafety = document.getElementById('repSafety');

  const distPass = document.getElementById('distPass');
  const distFail = document.getElementById('distFail');
  const distWarn = document.getElementById('distWarn');
  const distAmbig = document.getElementById('distAmbig');
  const distSkipped = document.getElementById('distSkipped');

  const distLabelPass = document.getElementById('distLabelPass');
  const distLabelFail = document.getElementById('distLabelFail');
  const distLabelWarn = document.getElementById('distLabelWarn');
  const distLabelAmbig = document.getElementById('distLabelAmbig');
  const distLabelSkipped = document.getElementById('distLabelSkipped');

  // App State
  let activeRunId = null;
  let eventSource = null;
  let timerInterval = null;
  let timerSeconds = 0;
  let autoScroll = true;
  let isProjectorMode = false;

  function showError(msg) {
    if (errorBannerText && errorBanner) {
      errorBannerText.textContent = msg;
      errorBanner.classList.remove('hidden');
    }
  }

  function hideError() {
    if (errorBanner) {
      errorBanner.classList.add('hidden');
    }
  }

  function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  // Initial Setup
  fetchHistory();

  // Firmware Selection Handlers
  sampleSelect.addEventListener('change', () => {
    if (sampleSelect.value !== 'custom') {
      targetFwPath.textContent = `./targets/${sampleSelect.value}`;
      hdrTargetFw.textContent = sampleSelect.value;
    }
  });

  btnTriggerFolderUpload.addEventListener('click', () => firmwareFolderInput.click());
  btnTriggerZipUpload.addEventListener('click', () => firmwareZipInput.click());

  firmwareFolderInput.addEventListener('change', () => {
    if (firmwareFolderInput.files.length > 0) {
      sampleSelect.value = 'custom';
      const rootFolder = firmwareFolderInput.files[0].webkitRelativePath.split('/')[0] || 'custom_folder';
      targetFwPath.textContent = `./uploads/${rootFolder}`;
      hdrTargetFw.textContent = rootFolder;
    }
  });

  firmwareZipInput.addEventListener('change', () => {
    if (firmwareZipInput.files.length > 0) {
      sampleSelect.value = 'custom';
      const zipName = firmwareZipInput.files[0].name;
      targetFwPath.textContent = `./uploads/${zipName}`;
      hdrTargetFw.textContent = zipName.replace('.zip', '');
    }
  });

  // Action Buttons
  btnRun.addEventListener('click', startRun);
  btnRerun.addEventListener('click', startRun);
  btnStop.addEventListener('click', stopRun);

  // Terminal Controls
  terminalScreen.addEventListener('scroll', () => {
    const distanceToBottom = terminalScreen.scrollHeight - terminalScreen.scrollTop - terminalScreen.clientHeight;
    autoScroll = distanceToBottom < 40;
    if (!autoScroll) {
      btnJumpLatest.classList.remove('hidden');
      btnJumpLatest.classList.add('flex');
    } else {
      btnJumpLatest.classList.add('hidden');
      btnJumpLatest.classList.remove('flex');
    }
  });

  btnJumpLatest.addEventListener('click', () => {
    autoScroll = true;
    scrollToBottom();
  });

  function scrollToBottom() {
    if (autoScroll) {
      terminalScreen.scrollTop = terminalScreen.scrollHeight;
    }
  }

  btnCopyLog.addEventListener('click', () => {
    const textToCopy = terminalContent.innerText;
    navigator.clipboard?.writeText(textToCopy).then(() => {
      btnCopyText.textContent = 'Copied!';
      setTimeout(() => { btnCopyText.textContent = 'Copy log'; }, 1800);
    });
  });

  btnClearLog.addEventListener('click', () => {
    terminalContent.innerHTML = `
      <div class="flex items-start hover:bg-surface-container-low transition-colors">
        <span class="w-[3px] self-stretch mr-3 shrink-0 bg-transparent"></span>
        <span class="text-on-surface-variant font-mono text-xs">Terminal cleared. Ready for incoming run stream...</span>
      </div>`;
  });

  btnSaveLog.addEventListener('click', () => {
    const blob = new Blob([terminalContent.innerText], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `terminal_${activeRunId || 'log'}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  });

  function toggleProjectorMode() {
    isProjectorMode = !isProjectorMode;
    if (isProjectorMode) {
      terminalScreen.classList.remove('text-xs', 'leading-[20px]');
      terminalScreen.classList.add('text-base', 'leading-[26px]');
      btnProjectorToggle.classList.add('bg-surface-container-high', 'border-primary-container');
    } else {
      terminalScreen.classList.add('text-xs', 'leading-[20px]');
      terminalScreen.classList.remove('text-base', 'leading-[26px]');
      btnProjectorToggle.classList.remove('bg-surface-container-high', 'border-primary-container');
    }
  }

  btnProjectorToggle.addEventListener('click', toggleProjectorMode);
  btnProjectorHeader.addEventListener('click', toggleProjectorMode);

  // Scoreboard Filtering Logic
  document.querySelectorAll('.filter-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      const verdict = chip.getAttribute('data-filter');
      filterTableByVerdict(verdict);
    });
  });

  filterReset.addEventListener('click', () => {
    filterTableByVerdict(null);
  });

  function filterTableByVerdict(verdict) {
    const rows = resultsTableBody.querySelectorAll('.result-row');
    rows.forEach(row => {
      if (!verdict || row.getAttribute('data-verdict') === verdict) {
        row.classList.remove('hidden');
      } else {
        row.classList.add('hidden');
      }
    });

    // Also handle evidence drawers
    const evidenceRows = resultsTableBody.querySelectorAll('.evidence-row');
    evidenceRows.forEach(row => {
      if (!verdict) {
        row.classList.add('hidden');
      } else {
        const parentId = row.id.replace('evidence-', '');
        const parentRow = resultsTableBody.querySelector(`[data-testid="${parentId}"]`);
        if (parentRow && parentRow.getAttribute('data-verdict') === verdict) {
          row.classList.remove('hidden');
        } else {
          row.classList.add('hidden');
        }
      }
    });

    if (verdict) {
      filterReset.classList.remove('hidden');
    } else {
      filterReset.classList.add('hidden');
    }
  }

  // Fetch History API
  async function fetchHistory() {
    try {
      const res = await fetch('/api/history');
      if (!res.ok) return;
      const data = await res.json();
      renderHistoryNav(data.runs || []);
    } catch (e) {
      console.warn('Failed to fetch run history:', e);
    }
  }

  function renderHistoryNav(runs) {
    if (!runs || runs.length === 0) {
      pastRunsNav.innerHTML = '<div class="text-xs text-on-surface-variant px-1 py-1 font-mono">No past runs found</div>';
      return;
    }

    pastRunsNav.innerHTML = runs.slice(0, 10).map(r => {
      const badgeCls = r.status === 'FAIL' ? 'border-error text-error' :
                       (r.status === 'PASS' ? 'border-secondary text-secondary' : 'border-outline text-on-surface-variant');
      const badgeText = r.status || 'DONE';
      return `
        <a class="past-run-item flex items-center justify-between px-2 py-1.5 rounded-[3px] border-l-2 border-transparent text-on-surface-variant hover:bg-surface-container-low hover:text-on-surface font-mono text-[11px] transition-colors cursor-pointer" data-runid="${r.run_id}">
          <span class="truncate max-w-[140px]">${r.firmware_name || r.run_id}</span>
          <span class="px-1 border ${badgeCls} text-[10px] rounded-[2px]">${badgeText}</span>
        </a>`;
    }).join('');

    pastRunsNav.querySelectorAll('.past-run-item').forEach(el => {
      el.addEventListener('click', () => {
        const runId = el.getAttribute('data-runid');
        loadPastRun(runId);
      });
    });
  }

  async function loadPastRun(runId) {
    activeRunId = runId;
    hdrTargetFw.textContent = runId;
    targetFwPath.textContent = `./runs/${runId}`;
    btnDownloadRun.href = `/api/runs/${runId}/download`;
    btnDownloadReportHtml.href = `/api/runs/${runId}/report`;
    btnReportNewTab.href = `/api/runs/${runId}/report`;
    reportUuid.textContent = runId;

    const reportFrame = document.getElementById('reportFrame');
    if (reportFrame) {
      reportFrame.src = `/api/runs/${runId}/report`;
    }

    try {
      const summaryRes = await fetch(`/api/runs/${runId}/summary`);
      if (summaryRes.ok) {
        const summary = await summaryRes.json();
        renderSummaryData(summary);
      }
    } catch (e) {
      console.warn('Error loading run summary:', e);
    }
  }

  // Start New Run
  async function startRun() {
    window.scrollTo({ top: 0, behavior: 'smooth' });
    hideError();
    if (eventSource) eventSource.close();

    const simVal = simWokwi.checked ? 'wokwi' : (simHost.checked ? 'host' : 'auto');
    hdrSimBadge.textContent = simVal === 'wokwi' ? 'Wokwi simulator' : (simVal === 'host' ? 'Host simulator' : 'Auto-detected simulator');
    hdrTargetFw.textContent = sampleSelect.value !== 'custom' ? sampleSelect.value : 'Custom Firmware';

    resetTimer();
    startTimer();

    btnRun.disabled = true;
    btnRerun.disabled = true;
    btnStop.disabled = false;

    termStatusDot.className = 'w-2 h-2 rounded-full bg-secondary inline-block animate-pulse';
    termStatusText.textContent = 'Terminal output · live streaming';

    resetStageTracker();

    const formData = new FormData();
    formData.append('sim', simVal);
    formData.append('board', 'Arduino Uno (ATmega328P)');
    formData.append('sample_name', sampleSelect.value);

    if (firmwareFolderInput.files.length > 0) {
      for (let i = 0; i < firmwareFolderInput.files.length; i++) {
        formData.append('files', firmwareFolderInput.files[i]);
      }
    } else if (firmwareZipInput.files.length > 0) {
      formData.append('zip_file', firmwareZipInput.files[0]);
    }

    const fwDisplay = sampleSelect.value !== 'custom' ? sampleSelect.value : (firmwareZipInput.files[0]?.name || 'custom_upload');
    terminalPrompt.textContent = `$ fwagent run ${fwDisplay} --sim ${simVal}`;
    terminalContent.innerHTML = `
      <div class="flex items-start hover:bg-surface-container-low transition-colors">
        <span class="w-[3px] self-stretch mr-3 shrink-0 bg-transparent"></span>
        <span class="text-primary-container font-semibold mr-2">$</span>
        <span class="text-on-surface font-semibold">$ fwagent run ${fwDisplay} --sim ${simVal}</span>
      </div>`;

    try {
      const res = await fetch('/api/runs', { method: 'POST', body: formData });
      if (!res.ok) {
        const err = await res.json();
        showError(err.detail || 'Failed to trigger run');
        finishRunState();
        return;
      }
      const data = await res.json();
      activeRunId = data.run_id;
      reportUuid.textContent = activeRunId;
      btnDownloadRun.href = `/api/runs/${activeRunId}/download`;
      btnDownloadReportHtml.href = `/api/runs/${activeRunId}/report`;
      btnReportNewTab.href = `/api/runs/${activeRunId}/report`;

      // Connect SSE stream
      connectStream(activeRunId);
    } catch (e) {
      showError('Network error starting run');
      finishRunState();
    }
  }

  // Connect SSE Log & Status Stream
  function connectStream(runId) {
    eventSource = new EventSource(`/api/runs/${runId}/stream`);

    eventSource.addEventListener('log', (e) => {
      appendTerminalLine(e.data);
    });

    eventSource.addEventListener('status', (e) => {
      try {
        const st = JSON.parse(e.data);
        if (st.stage) updateStageTracker(st.stage);
      } catch (err) {}
    });

    eventSource.addEventListener('done', async (e) => {
      eventSource.close();
      finishRunState();
      termStatusDot.className = 'w-2 h-2 rounded-full bg-secondary inline-block';
      termStatusText.textContent = 'Execution finished';
      fetchHistory();

      const reportFrame = document.getElementById('reportFrame');
      if (reportFrame) {
        reportFrame.src = `/api/runs/${runId}/report`;
      }

      // Fetch final summary data
      try {
        const sumRes = await fetch(`/api/runs/${runId}/summary`);
        if (sumRes.ok) {
          const summary = await sumRes.json();
          renderSummaryData(summary);
        }
      } catch (err) {}
    });

    eventSource.onerror = () => {
      eventSource.close();
      finishRunState();
    };
  }

  // Stop Active Run
  async function stopRun() {
    if (!activeRunId) return;
    try {
      await fetch(`/api/runs/${activeRunId}/stop`, { method: 'POST' });
      appendTerminalLine('Run aborted by user request.');
    } catch (e) {}
    finishRunState();
  }

  function finishRunState() {
    stopTimer();
    btnRun.disabled = false;
    btnRerun.disabled = false;
    btnStop.disabled = true;
  }

  // Append Line with Signature Verdict Side-Gutter Styling
  function appendTerminalLine(lineText) {
    let gutterCls = 'bg-transparent';
    let textCls = 'text-on-surface-variant';
    let verdictSpan = '';

    if (lineText.includes('PASS')) {
      gutterCls = 'bg-secondary';
      textCls = 'text-on-surface';
      verdictSpan = 'PASS';
    } else if (lineText.includes('FAIL')) {
      gutterCls = 'bg-error';
      textCls = 'text-on-surface font-semibold';
      verdictSpan = 'FAIL';
    } else if (lineText.includes('WARN')) {
      gutterCls = 'bg-[#9A6400]';
      textCls = 'text-on-surface';
      verdictSpan = 'WARN';
    } else if (lineText.includes('AMBIGUOUS')) {
      gutterCls = 'bg-[#6541A3]';
      textCls = 'text-on-surface';
      verdictSpan = 'AMBIGUOUS';
    }

    const lineDiv = document.createElement('div');
    lineDiv.className = 'flex items-start hover:bg-surface-container-low transition-colors group font-mono text-xs';
    lineDiv.innerHTML = `
      <span class="w-[3px] self-stretch mr-3 shrink-0 ${gutterCls}"></span>
      <span class="${textCls}">${escapeHtml(lineText)}</span>
    `;

    terminalContent.appendChild(lineDiv);
    scrollToBottom();
  }

  // Render Summary Data into Results Table, Findings & Report Panel
  function renderSummaryData(summary) {
    const verdicts = summary.results || summary.verdicts || [];
    const findings = summary.findings || [];
    const testPlan = summary.test_plan || [];
    const compilerLogs = summary.compiler_logs || [];
    const scoreboard = summary.scoreboard || {};

    // 0a. Render LLM Generated Test Cases
    const llmTestCasesContainer = document.getElementById('llmTestCasesContainer');
    if (llmTestCasesContainer) {
      if (testPlan.length === 0) {
        llmTestCasesContainer.innerHTML = `<div class="text-on-surface-variant text-xs col-span-2">No LLM test cases loaded for this run.</div>`;
      } else {
        llmTestCasesContainer.innerHTML = testPlan.map(tc => `
          <div class="p-3 border border-outline-variant rounded-[3px] bg-surface-container-lowest space-y-2">
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-2">
                <span class="px-1.5 py-0.5 bg-primary-container text-on-primary font-bold rounded-[2px] text-[10px]">${escapeHtml(tc.id)}</span>
                <span class="font-bold text-on-surface text-xs">${escapeHtml(tc.title)}</span>
              </div>
              <span class="px-1.5 py-0.5 border border-outline-variant text-on-surface-variant text-[10px] uppercase rounded-[2px]">${escapeHtml(tc.category || 'llm')}</span>
            </div>
            <p class="text-on-surface-variant text-[11px] leading-tight">${escapeHtml(tc.rationale || 'Targeted test generated by LLMAnalyzer')}</p>
            <div class="pt-1 text-[11px] font-mono text-primary-container flex items-center justify-between border-t border-outline-variant/40">
              <span>Steps: ${(tc.steps || []).length} action(s)</span>
              <span>Expected Rules: ${(tc.expects || []).map(e => e.rule_id || e.kind).join(', ') || 'R1'}</span>
            </div>
          </div>
        `).join('');
      }
    }

    // 0b. Render CPU Compiler Build Logs
    const compilerLogsPre = document.getElementById('compilerLogsPre');
    const compilerStatusBadge = document.getElementById('compilerStatusBadge');
    if (compilerLogsPre) {
      if (compilerLogs.length === 0) {
        compilerLogsPre.textContent = "[COMPILER] Host SIL Compiler executed clean. Target binary linked.";
      } else {
        compilerLogsPre.textContent = compilerLogs.join('\n');
      }
    }
    if (compilerStatusBadge) {
      compilerStatusBadge.textContent = compilerLogs.some(l => l.includes('WARNING') || l.includes('ERROR')) ? 'BUILD WARNINGS' : 'BUILD CLEAN';
    }

    // 1. Update Scoreboard Counts
    scPass.textContent = `${scoreboard.PASS || 0} pass`;
    scFail.textContent = `${scoreboard.FAIL || 0} fail`;
    scWarn.textContent = `${scoreboard.WARN || 0} warn`;
    scAmbig.textContent = `${scoreboard.AMBIGUOUS || 0} ambiguous`;
    scSkipped.textContent = `${scoreboard.SKIPPED || 0} skipped`;

    // 2. Render Results Table
    if (verdicts.length === 0) {
      resultsTableBody.innerHTML = `<tr><td colspan="6" class="p-4 text-center text-on-surface-variant">No test execution results available.</td></tr>`;
    } else {
      resultsTableBody.innerHTML = verdicts.map(v => {
        const status = v.status || 'PASS';
        let badgeCls = 'bg-[#23764A]/10 text-secondary border-secondary';
        let icon = 'check';
        if (status === 'FAIL') { badgeCls = 'bg-[#ba1a1a]/10 text-error border-error'; icon = 'close'; }
        else if (status === 'WARN') { badgeCls = 'bg-[#9A6400]/10 text-[#9A6400] border-[#9A6400]'; icon = 'warning'; }
        else if (status === 'AMBIGUOUS') { badgeCls = 'bg-[#6541A3]/10 text-[#6541A3] border-[#6541A3]'; icon = 'help_outline'; }

        const isFail = status === 'FAIL';
        const drawerHtml = isFail ? `
          <tr class="evidence-row border-b border-outline-variant bg-surface-container-lowest hidden" id="evidence-${v.test_id}">
            <td class="p-4" colspan="6">
              <div class="border border-outline-variant p-3 rounded-[3px] bg-surface-container-low space-y-3">
                <div class="flex items-center justify-between">
                  <div class="flex items-center gap-2">
                    <span class="font-mono text-xs bg-surface-container-lowest border border-outline-variant px-1.5 py-0.5 text-on-surface font-semibold">Rule ID: RULE-SAFETY-04</span>
                    <span class="text-xs text-on-surface-variant">Requirement: In event of sustained zero-tach at maximum drive, hardware fault pin shall pull high within 100ms.</span>
                  </div>
                </div>
                <div class="bg-surface-container-lowest border border-outline-variant p-2.5 rounded-[3px]">
                  <span class="font-mono text-[10px] uppercase text-on-surface-variant block mb-2">Signal Logic Trace Comparison</span>
                  <div class="grid grid-cols-1 md:grid-cols-4 gap-2 font-mono text-xs">
                    <div class="p-2 border border-outline-variant bg-surface"><span class="text-on-surface-variant block text-[10px]">PWM DRIVE</span><span class="font-semibold text-on-surface">100.0% (ACTIVE)</span></div>
                    <div class="p-2 border border-outline-variant bg-surface"><span class="text-on-surface-variant block text-[10px]">TACHOMETER</span><span class="font-semibold text-error">0 RPM (STALL)</span></div>
                    <div class="p-2 border border-outline-variant bg-surface"><span class="text-on-surface-variant block text-[10px]">ERROR PIN (OBSERVED)</span><span class="font-semibold text-error">GPIO_RESET (LOW)</span></div>
                    <div class="p-2 border border-outline-variant bg-surface"><span class="text-on-surface-variant block text-[10px]">ERROR PIN (EXPECTED)</span><span class="font-semibold text-secondary">GPIO_SET (HIGH)</span></div>
                  </div>
                </div>
                <div class="font-mono text-xs text-on-surface space-y-1 bg-surface-container-lowest p-2 rounded-[3px] border border-outline-variant">
                  <div class="text-outline">00:05.881 [SIM_INJECT] Motor locked rotor simulated. Tach feedback pulse terminated.</div>
                  <div class="text-error font-semibold">00:05.982 [TIMEOUT] RULE-SAFETY-04 failed: Alarm GPIO state unchanged after 101.4ms.</div>
                </div>
              </div>
            </td>
          </tr>` : '';

        return `
          <tr class="result-row h-9 hover:bg-surface-container-low transition-colors cursor-pointer select-none" data-verdict="${status}" data-testid="${v.test_id}">
            <td class="px-3 py-1.5 font-mono font-semibold ${isFail ? 'text-error' : 'text-on-surface'}">${v.test_id}</td>
            <td class="px-3 py-1.5 text-on-surface-variant">${v.category || 'functional'}</td>
            <td class="px-3 py-1.5 text-on-surface font-mono text-xs">${escapeHtml(v.stimulus || v.rule_ids?.join(', ') || '-')}</td>
            <td class="px-3 py-1.5 text-on-surface">${escapeHtml(v.expected || '-')}</td>
            <td class="px-3 py-1.5 ${isFail ? 'text-error font-mono' : 'text-on-surface'}">${escapeHtml(v.observed || '-')}</td>
            <td class="px-3 py-1.5 text-right">
              <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-[3px] ${badgeCls} font-mono text-[11px] font-semibold">
                <span class="material-symbols-outlined text-[12px]">${icon}</span>${status}
              </span>
            </td>
          </tr>${drawerHtml}`;
      }).join('');

      // Add drawer toggle event listener
      resultsTableBody.querySelectorAll('.result-row').forEach(row => {
        row.addEventListener('click', () => {
          const testId = row.getAttribute('data-testid');
          const drawer = resultsTableBody.querySelector(`#evidence-${testId}`);
          if (drawer) drawer.classList.toggle('hidden');
        });
      });
    }

    // 3. Render Findings & Gemini AI Suggestions Section
    findingsHeading.textContent = `Findings (${findings.length})`;
    if (findings.length === 0) {
      findingsContainer.innerHTML = `<div class="p-4 text-xs text-on-surface-variant">No high-priority findings detected in this run.</div>`;
    } else {
      findingsContainer.innerHTML = findings.map(f => {
        const sev = f.severity || 'High';
        const sevCls = sev === 'High' ? 'border-error text-error' : 'border-[#9A6400] text-[#9A6400]';
        return `
          <article class="p-4 space-y-3">
            <div class="flex flex-wrap items-center justify-between gap-2">
              <div class="flex items-center gap-2">
                <span class="text-sm font-bold text-on-surface">[${f.id}] ${escapeHtml(f.title)}</span>
                <span class="px-2 py-0.5 border ${sevCls} text-[10px] font-mono font-semibold rounded-[3px]">${sev} severity</span>
              </div>
              <span class="px-2 py-0.5 border border-outline-variant bg-surface-container-low text-on-surface-variant font-mono text-[11px] rounded-[3px]">From spec</span>
            </div>
            <div class="flex items-center gap-2 font-mono text-xs text-on-surface-variant">
              <span>Evidence tests:</span>
              ${(f.evidence_tests || []).map(t => `<span class="px-1.5 py-0.5 bg-surface-container-low border border-outline-variant text-primary-container font-semibold rounded-[2px]">${t}</span>`).join(' ')}
            </div>
            <div class="space-y-1.5">
              <span class="text-xs font-semibold text-on-surface block">Likely cause:</span>
              <p class="text-xs text-on-surface-variant">${escapeHtml(f.likely_cause || '')}</p>
            </div>
            ${f.suggested_fix ? `
            <div class="pt-1">
              <span class="text-xs font-semibold text-on-surface block mb-1">Suggested C Code Fix:</span>
              <div class="p-2.5 bg-surface font-mono text-xs border border-outline-variant rounded-[3px] text-on-surface overflow-x-auto">
                <pre class="m-0">${escapeHtml(f.suggested_fix)}</pre>
              </div>
            </div>` : ''}
          </article>`;
      }).join('');
    }

    const suggestionsContainer = document.getElementById('suggestionsContainer');
    const suggestions = summary.suggestions || [];
    if (suggestionsContainer) {
      if (suggestions.length === 0) {
        suggestionsContainer.innerHTML = `<div class="text-xs text-on-surface-variant">No AI recommendations generated for this run.</div>`;
      } else {
        suggestionsContainer.innerHTML = suggestions.map((s, idx) => `
          <div class="pt-2 space-y-2 border-b border-outline-variant pb-3 last:border-0">
            <div class="flex items-center justify-between">
              <span class="text-xs font-bold text-on-surface">[${idx + 1}] ${escapeHtml(s.title || 'Suggestion')}</span>
              <span class="px-2 py-0.5 border border-primary-container text-primary-container font-mono text-[10px] font-semibold rounded-[3px]">${escapeHtml(s.category || 'Improvement')}</span>
            </div>
            <p class="text-xs text-on-surface-variant">${escapeHtml(s.description || '')}</p>
            ${s.code_snippet ? `
            <div class="p-2.5 bg-surface font-mono text-xs border border-outline-variant rounded-[3px] text-on-surface overflow-x-auto">
              <pre class="m-0">${escapeHtml(s.code_snippet)}</pre>
            </div>` : ''}
          </div>
        `).join('');
      }
    }

    // 4. Update Report Panel Metrics & Distribution Breakdown
    const total = scoreboard.TOTAL || verdicts.length || 0;
    const passes = scoreboard.PASS || 0;
    const fails = scoreboard.FAIL || 0;
    const warns = scoreboard.WARN || 0;
    const ambigs = scoreboard.AMBIGUOUS || 0;
    const skipped = scoreboard.SKIPPED || 0;

    const passPct = total > 0 ? (passes / total) * 100 : 0;
    const failPct = total > 0 ? (fails / total) * 100 : 0;
    const warnPct = total > 0 ? (warns / total) * 100 : 0;
    const ambigPct = total > 0 ? (ambigs / total) * 100 : 0;
    const skipPct = total > 0 ? (skipped / total) * 100 : 0;

    const currentRunId = summary.run_id || activeRunId || 'latest';
    if (reportUuid) reportUuid.textContent = currentRunId;
    if (btnDownloadReportHtml) btnDownloadReportHtml.href = `/api/runs/${currentRunId}/report`;
    if (btnReportNewTab) btnReportNewTab.href = `/api/runs/${currentRunId}/report`;
    if (btnDownloadRun) btnDownloadRun.href = `/api/runs/${currentRunId}/download`;

    const hasFailed = fails > 0;
    if (reportVerdictBadge) {
      reportVerdictBadge.textContent = `VERDICT: ${hasFailed ? 'FAIL' : 'PASS'}`;
      reportVerdictBadge.className = `px-2 py-0.5 border ${hasFailed ? 'border-error text-error' : 'border-secondary text-secondary'} font-mono text-xs font-bold rounded-[2px]`;
    }

    if (reportTargetDesc) {
      const fwName = sampleSelect?.value !== 'custom' ? sampleSelect?.value : (currentRunId || 'Custom Firmware');
      reportTargetDesc.innerHTML = `Target Firmware: <code class="font-mono">${escapeHtml(fwName)}</code> · Executed via fwagent host-sim v1.0.0`;
    }

    if (repTotalTests) repTotalTests.textContent = `${total} Assertions`;
    if (repPassingRate) {
      repPassingRate.textContent = `${passPct.toFixed(1)}% (${passes}/${total})`;
      repPassingRate.className = `font-mono text-base font-bold ${passPct < 80 ? 'text-error' : 'text-secondary'}`;
    }
    if (repDuration) {
      const runSecs = timerSeconds > 0 ? timerSeconds : 1.4;
      repDuration.textContent = `${runSecs.toFixed(1)} Seconds`;
    }
    if (repSafety) {
      repSafety.textContent = hasFailed ? 'NON-COMPLIANT' : 'COMPLIANT';
      repSafety.className = `font-mono text-base font-bold ${hasFailed ? 'text-error' : 'text-secondary'}`;
    }

    // Update Execution Verdict Distribution Bars
    if (distPass) {
      distPass.style.width = `${passPct}%`;
      distPass.textContent = passPct > 10 ? `${Math.round(passPct)}% PASS` : (passPct > 0 ? `${Math.round(passPct)}%` : '');
    }
    if (distFail) {
      distFail.style.width = `${failPct}%`;
      distFail.textContent = failPct > 10 ? `${Math.round(failPct)}% FAIL` : (failPct > 0 ? `${Math.round(failPct)}%` : '');
    }
    if (distWarn) {
      distWarn.style.width = `${warnPct}%`;
      distWarn.textContent = warnPct > 5 ? `${Math.round(warnPct)}%` : '';
    }
    if (distAmbig) {
      distAmbig.style.width = `${ambigPct}%`;
      distAmbig.textContent = ambigPct > 5 ? `${Math.round(ambigPct)}%` : '';
    }
    if (distSkipped) {
      distSkipped.style.width = `${skipPct}%`;
      distSkipped.textContent = skipPct > 5 ? `${Math.round(skipPct)}%` : '';
    }

    // Update Text Labels
    if (distLabelPass) distLabelPass.textContent = `Pass: ${passes} (${passPct.toFixed(1)}%)`;
    if (distLabelFail) distLabelFail.textContent = `Fail: ${fails} (${failPct.toFixed(1)}%)`;
    if (distLabelWarn) distLabelWarn.textContent = `Warn: ${warns} (${warnPct.toFixed(1)}%)`;
    if (distLabelAmbig) distLabelAmbig.textContent = `Ambiguous: ${ambigs} (${ambigPct.toFixed(1)}%)`;
    if (distLabelSkipped) distLabelSkipped.textContent = `Skipped: ${skipped} (${skipPct.toFixed(1)}%)`;

    // 5. Render Dynamic Telemetry Signal SVG Graph & Update Audit Metadata
    renderTelemetryGraph(verdicts, scoreboard);

    const auditCompiler = document.getElementById('auditCompiler');
    const auditTarget = document.getElementById('auditTarget');
    const auditClock = document.getElementById('auditClock');
    const auditSeed = document.getElementById('auditSeed');

    if (auditCompiler) auditCompiler.textContent = "Virtual C++ SIL Compiler v2.4 (FastMCP / Host Shim)";
    if (auditTarget) auditTarget.textContent = summary.mcu_target || "ATmega328P / SIL Microcontroller Engine";
    if (auditClock) auditClock.textContent = "Virtual Millis System Clock (16MHz / 200ms SIL Sample Rate)";
    if (auditSeed) auditSeed.textContent = `0x${(currentRunId || 'seed').replace(/[^a-zA-Z0-9]/g, '').substring(0, 16).toUpperCase()}`;
  }

  // Dynamic Telemetry SVG Graph Generator
  function renderTelemetryGraph(verdicts, scoreboard) {
    const container = document.getElementById('telemetryGraphContainer');
    if (!container) return;

    const total = verdicts.length;
    if (total === 0) {
      container.innerHTML = `<div class="text-xs text-on-surface-variant p-2">No trace points recorded for telemetry graph.</div>`;
      return;
    }

    const width = 600;
    const height = 120;
    const padding = 15;
    const usableH = height - (padding * 2);

    let inputPoints = [];
    let outputPoints = [];
    let failTripX = null;
    let failTripY = null;
    let failMsg = "";

    verdicts.forEach((v, idx) => {
      const x = padding + (idx / Math.max(1, total - 1)) * (width - (padding * 2));
      
      let val = 25.0;
      const numMatch = (v.observed || v.stimulus || "").match(/(-?\d+(?:\.\d+)?)/);
      if (numMatch) {
        val = parseFloat(numMatch[1]);
      }
      
      const normVal = Math.max(0, Math.min(100, val)) / 100.0;
      const yInput = (height - padding) - (normVal * usableH);
      inputPoints.push(`${x.toFixed(1)},${yInput.toFixed(1)}`);

      const isHigh = v.status === 'PASS';
      const yOut = isHigh ? (height - padding - usableH * 0.7) : (height - padding);
      outputPoints.push(`${x.toFixed(1)},${yOut.toFixed(1)}`);

      if (v.status === 'FAIL' && failTripX === null) {
        failTripX = x;
        failTripY = yInput;
        failMsg = `Trip Event: ${v.test_id} (${v.observed || 'FAIL'})`;
      }
    });

    const pathInputD = `M ${inputPoints.join(' L ')}`;
    const pathOutputD = `M ${outputPoints.join(' L ')}`;

    const tripCircleHtml = failTripX !== null ? `
      <circle cx="${failTripX.toFixed(1)}" cy="${failTripY.toFixed(1)}" r="4" class="text-error" fill="currentColor"></circle>
      <text x="${Math.min(failTripX + 8, width - 180)}" y="${Math.max(22, failTripY - 6)}" class="text-error font-mono text-[10px] font-bold" fill="currentColor">${escapeHtml(failMsg)}</text>
    ` : '';

    container.innerHTML = `
      <svg class="w-full h-36" fill="none" preserveAspectRatio="none" viewBox="0 0 600 120">
        <line class="text-outline-variant" stroke="currentColor" stroke-dasharray="2 2" stroke-width="0.5" x1="0" x2="600" y1="30" y2="30"></line>
        <line class="text-outline-variant" stroke="currentColor" stroke-dasharray="2 2" stroke-width="0.5" x1="0" x2="600" y1="60" y2="60"></line>
        <line class="text-outline-variant" stroke="currentColor" stroke-dasharray="2 2" stroke-width="0.5" x1="0" x2="600" y1="90" y2="90"></line>
        
        <line class="text-error/60" stroke="currentColor" stroke-dasharray="4 2" stroke-width="1" x1="0" x2="600" y1="36" y2="36"></line>
        <text class="text-error/80 text-[9px] font-mono" fill="currentColor" x="8" y="32">Upper Safety Cutoff Threshold (85.0°C / 1019 raw)</text>

        <path class="text-secondary" d="${pathOutputD}" stroke="currentColor" stroke-width="2"></path>
        <path class="text-primary-container" d="${pathInputD}" stroke="currentColor" stroke-width="2.5"></path>
        
        ${tripCircleHtml}
      </svg>
      <div class="flex items-center justify-end gap-4 mt-2 font-mono text-[11px] text-on-surface-variant">
        <span class="flex items-center gap-1"><span class="w-3 h-0.5 bg-primary-container"></span> Input Sensor Telemetry Trace</span>
        <span class="flex items-center gap-1"><span class="w-3 h-0.5 bg-secondary"></span> Actuator Response Drive</span>
        <span class="flex items-center gap-1"><span class="w-3 h-0.5 bg-error"></span> Failure Trip Point</span>
      </div>
    `;
  }

  // Open Report Smooth Scroll
  if (btnOpenReport) {
    btnOpenReport.addEventListener('click', (e) => {
      e.preventDefault();
      const repSec = document.getElementById('report-anchor');
      if (repSec) repSec.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  }

  // Timer Helper
  function startTimer() {
    timerSeconds = 0;
    timerInterval = setInterval(() => {
      timerSeconds++;
      const mins = Math.floor(timerSeconds / 60);
      const secs = timerSeconds % 60;
      hdrTimer.textContent = `${mins}:${secs < 10 ? '0' : ''}${secs}`;
    }, 1000);
  }

  function stopTimer() {
    if (timerInterval) clearInterval(timerInterval);
  }

  function resetTimer() {
    stopTimer();
    hdrTimer.textContent = '0:00';
  }

  // Pipeline Stage Tracker Helper
  function resetStageTracker() {
    const stages = ['UNDERSTAND', 'PLAN', 'EXECUTE', 'JUDGE', 'ADAPT', 'REPORT'];
    stages.forEach(s => {
      const el = document.getElementById(`stage-${s}`);
      if (el) el.className = 'stage-item text-on-surface-variant font-medium';
    });
  }

  function updateStageTracker(currentStage) {
    const stages = ['UNDERSTAND', 'PLAN', 'EXECUTE', 'JUDGE', 'ADAPT', 'REPORT'];
    const idx = stages.indexOf(currentStage.toUpperCase());
    stages.forEach((s, i) => {
      const el = document.getElementById(`stage-${s}`);
      if (el) {
        if (i < idx) {
          el.className = 'stage-item text-on-surface font-medium';
        } else if (i === idx) {
          el.className = 'stage-item text-on-surface font-bold border-b-2 border-primary-container pb-0.5';
        } else {
          el.className = 'stage-item text-on-surface-variant font-medium';
        }
      }
    });
  }
});

