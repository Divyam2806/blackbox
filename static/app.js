// BlackBox FW-Agent Web UI Client JavaScript

document.addEventListener('DOMContentLoaded', () => {
    // DOM Element Handles
    const sampleSelect = document.getElementById('sampleSelect');
    const firmwareFolderInput = document.getElementById('firmwareFolderInput');
    const firmwareZipInput = document.getElementById('firmwareZipInput');
    const boardSelect = document.getElementById('boardSelect');
    const simulatorSelect = document.getElementById('simulatorSelect');
    
    const btnRun = document.getElementById('btnRun');
    const btnStop = document.getElementById('btnStop');
    const historySelect = document.getElementById('historySelect');
    const btnLoadHistory = document.getElementById('btnLoadHistory');
    const btnReplay = document.getElementById('btnReplay');

    const hdrTargetFw = document.getElementById('hdrTargetFw');
    const hdrBoard = document.getElementById('hdrBoard');
    const hdrSim = document.getElementById('hdrSim');
    const progressBarFill = document.getElementById('progressBarFill');
    const progressText = document.getElementById('progressText');
    const errorBanner = document.getElementById('errorBanner');
    const errorBannerText = document.getElementById('errorBannerText');

    const scTotal = document.getElementById('scTotal');
    const scPass = document.getElementById('scPass');
    const scFail = document.getElementById('scFail');
    const scWarn = document.getElementById('scWarn');
    const scAmbig = document.getElementById('scAmbig');
    const scInconclusive = document.getElementById('scInconclusive');
    const scSkipped = document.getElementById('scSkipped');

    const promptLine = document.getElementById('promptLine');
    const terminalWindow = document.getElementById('terminalWindow');
    const terminalContent = document.getElementById('terminalContent');
    const btnToggleFont = document.getElementById('btnToggleFont');
    const btnJumpBottom = document.getElementById('btnJumpBottom');
    const btnCopyTerminal = document.getElementById('btnCopyTerminal');
    const btnClearTerminal = document.getElementById('btnClearTerminal');

    const btnToggleReportIframe = document.getElementById('btnToggleReportIframe');
    const btnDownloadReport = document.getElementById('btnDownloadReport');
    const btnDownloadZip = document.getElementById('btnDownloadZip');
    const iframeContainer = document.getElementById('iframeContainer');
    const reportIframe = document.getElementById('reportIframe');
    const findingsGrid = document.getElementById('findingsGrid');

    // App State
    let activeRunId = null;
    let eventSource = null;
    let autoScroll = true;
    let isProjectorFont = false;

    // Load Initial Samples & History
    fetchSamples();
    fetchHistory();

    // Auto-scroll Detection
    terminalWindow.addEventListener('scroll', () => {
        const distanceToBottom = terminalWindow.scrollHeight - terminalWindow.scrollTop - terminalWindow.clientHeight;
        autoScroll = distanceToBottom < 30;
    });

    btnJumpBottom.addEventListener('click', () => {
        autoScroll = true;
        scrollToBottom();
    });

    function scrollToBottom() {
        if (autoScroll) {
            terminalWindow.scrollTop = terminalWindow.scrollHeight;
        }
    }

    btnToggleFont.addEventListener('click', () => {
        isProjectorFont = !isProjectorFont;
        terminalWindow.classList.toggle('projector-font', isProjectorFont);
    });

    btnClearTerminal.addEventListener('click', () => {
        terminalContent.innerHTML = '';
    });

    btnCopyTerminal.addEventListener('click', () => {
        navigator.clipboard.writeText(terminalContent.innerText);
        alert('Terminal output copied to clipboard!');
    });

    btnToggleReportIframe.addEventListener('click', () => {
        iframeContainer.classList.toggle('hidden');
    });

    // Event Handlers for Run / Stop
    btnRun.addEventListener('click', startRun);
    btnStop.addEventListener('click', stopRun);
    btnLoadHistory.addEventListener('click', loadSelectedHistory);
    btnReplay.addEventListener('click', replaySelectedHistory);

    // API Calls
    async function fetchSamples() {
        try {
            const res = await fetch('/api/samples');
            const data = await res.json();
            if (data.samples && data.samples.length > 0) {
                // Pre-populated
            }
        } catch (err) {
            console.error('Failed to fetch samples:', err);
        }
    }

    async function fetchHistory() {
        try {
            const res = await fetch('/api/runs');
            const runs = await res.json();
            historySelect.innerHTML = '';

            if (runs.length === 0) {
                historySelect.innerHTML = '<option value="">No past runs</option>';
                return;
            }

            runs.forEach(r => {
                const opt = document.createElement('option');
                opt.value = r.id;
                opt.textContent = `${r.time} — ${r.id} (PASS:${r.scoreboard.PASS} FAIL:${r.scoreboard.FAIL})`;
                historySelect.appendChild(opt);
            });
        } catch (err) {
            console.error('Failed to fetch history:', err);
        }
    }

    async function startRun() {
        hideError();
        btnRun.disabled = true;
        btnStop.disabled = false;
        terminalContent.innerHTML = '';
        resetStageTracker();

        const formData = new FormData();
        const sampleVal = sampleSelect.value;
        const simVal = simulatorSelect.value;
        const boardVal = boardSelect.value;

        formData.append('sim', simVal);
        formData.append('board', boardVal);
        formData.append('sample_name', sampleVal);

        if (firmwareFolderInput.files.length > 0) {
            for (let i = 0; i < firmwareFolderInput.files.length; i++) {
                formData.append('files', firmwareFolderInput.files[i]);
            }
        } else if (firmwareZipInput.files.length > 0) {
            formData.append('zip_file', firmwareZipInput.files[0]);
        }

        const fwDisplay = sampleVal !== 'custom' ? sampleVal : (firmwareZipInput.files[0]?.name || 'Custom Folder');
        hdrTargetFw.textContent = fwDisplay;
        hdrBoard.textContent = boardVal;
        hdrSim.textContent = simVal === 'host' ? 'Host-HAL SIL' : 'Wokwi Simulator';
        promptLine.textContent = `$ fwagent run ${fwDisplay} --sim ${simVal}`;

        try {
            const res = await fetch('/api/runs', { method: 'POST', body: formData });
            if (!res.ok) {
                const errData = await res.json();
                showError(errData.detail || 'Upload failed');
                btnRun.disabled = false;
                btnStop.disabled = true;
                return;
            }

            const data = await res.json();
            activeRunId = data.run_id;
            connectSSE(`/api/runs/${activeRunId}/stream`);

        } catch (err) {
            showError('Network error starting run: ' + err.message);
            btnRun.disabled = false;
            btnStop.disabled = true;
        }
    }

    async function stopRun() {
        if (!activeRunId) return;
        try {
            await fetch(`/api/runs/${activeRunId}/stop`, { method: 'POST' });
            btnStop.disabled = true;
            appendLogLine('EXECUTION STOPPED BY USER.', 'log-warn');
        } catch (err) {
            console.error('Stop error:', err);
        }
    }

    function connectSSE(url) {
        if (eventSource) eventSource.close();
        eventSource = new EventSource(url);

        eventSource.onmessage = (e) => {
            // Default message
        };

        eventSource.addEventListener('log', (e) => {
            const data = JSON.parse(e.data);
            appendLogLine(data.line);
        });

        eventSource.addEventListener('status', (e) => {
            const data = JSON.parse(e.data);
            updateStageTracker(data.stage_states);
            if (data.current_test) {
                progressText.textContent = `${data.completed_tests}/${data.total_tests} (${data.current_test})`;
                const pct = data.total_tests ? Math.min(100, Math.round((data.completed_tests / data.total_tests) * 100)) : 0;
                progressBarFill.style.width = pct + '%';
            }
        });

        eventSource.addEventListener('done', (e) => {
            const data = JSON.parse(e.data);
            appendLogLine(`[Process exited with code ${data.exit_code}]`, data.exit_code === 0 ? 'log-pass' : 'log-fail');
            btnRun.disabled = false;
            btnStop.disabled = true;
            if (eventSource) eventSource.close();

            loadSummary(activeRunId);
            fetchHistory();
        });

        eventSource.onerror = (err) => {
            console.warn('SSE stream error or disconnect, retrying...', err);
        };
    }

    function appendLogLine(text, customClass = '') {
        const span = document.createElement('span');
        let cls = customClass;

        if (!cls) {
            if (text.includes('PASS') || text.includes('100%')) cls = 'log-pass';
            else if (text.includes('FAIL') || text.includes('ERR')) cls = 'log-fail';
            else if (text.includes('WARN')) cls = 'log-warn';
            else if (text.includes('STAGE') || text.includes('====')) cls = 'log-stage';
            else if (text.includes('ROUND') || text.includes('ADAPT')) cls = 'log-adapt';
        }

        if (cls) span.className = cls;
        span.textContent = text + '\n';
        terminalContent.appendChild(span);
        scrollToBottom();

        // Check progress parsing from text
        if (text.includes('Test ') && text.includes('/')) {
            const match = text.match(/Test (\d+)\/(\d+)/);
            if (match) {
                const cur = parseInt(match[1]);
                const tot = parseInt(match[2]);
                progressText.textContent = `${cur}/${tot}`;
                progressBarFill.style.width = Math.min(100, Math.round((cur / tot) * 100)) + '%';
            }
        }
    }

    function updateStageTracker(states) {
        if (!states) return;
        Object.keys(states).forEach(st => {
            const el = document.getElementById(`stage-${st}`);
            if (el) {
                el.className = `stage-step ${states[st]}`;
            }
        });
    }

    function resetStageTracker() {
        ['UNDERSTAND', 'PLAN', 'EXECUTE', 'OBSERVE', 'JUDGE', 'ADAPT', 'REPORT'].forEach(st => {
            const el = document.getElementById(`stage-${st}`);
            if (el) el.className = 'stage-step pending';
        });
        progressBarFill.style.width = '0%';
        progressText.textContent = 'Ready';
    }

    async function loadSummary(runId) {
        try {
            const res = await fetch(`/api/runs/${runId}/summary`);
            if (!res.ok) return;
            const data = await res.json();

            const sc = data.scoreboard || {};
            scTotal.textContent = sc.TOTAL || 0;
            scPass.textContent = sc.PASS || 0;
            scFail.textContent = sc.FAIL || 0;
            scWarn.textContent = sc.WARN || 0;
            scAmbig.textContent = sc.AMBIGUOUS || 0;
            scInconclusive.textContent = sc.INCONCLUSIVE || 0;
            scSkipped.textContent = sc.SKIPPED || 0;

            // Report links
            btnDownloadReport.href = `/api/runs/${runId}/report`;
            btnDownloadZip.href = `/api/runs/${runId}/download`;
            reportIframe.src = `/api/runs/${runId}/report`;

            // Render Findings Cards
            renderFindings(data.findings || []);

        } catch (err) {
            console.error('Failed to load run summary:', err);
        }
    }

    function renderFindings(findings) {
        findingsGrid.innerHTML = '';
        if (findings.length === 0) {
            findingsGrid.innerHTML = '<div class="empty-state">No high-priority findings detected. Clean run!</div>';
            return;
        }

        findings.forEach(f => {
            const card = document.createElement('div');
            card.className = 'finding-card-ui';
            const lines = f.firmware_lines ? f.firmware_lines.join(', ') : 'N/A';
            const tests = f.evidence_tests ? f.evidence_tests.join(', ') : 'N/A';

            card.innerHTML = `
                <h4>[${f.id}] ${f.title} (Severity: ${f.severity})</h4>
                <p><strong>Evidence Tests:</strong> ${tests}</p>
                <p><strong>Likely Cause:</strong> ${f.likely_cause}</p>
                <p><strong>Firmware Lines:</strong> <span style="color:#38bdf8; font-weight:bold;">Lines ${lines}</span></p>
                <div class="code-box-ui">${escapeHtml(f.suggested_fix || '')}</div>
            `;
            findingsGrid.appendChild(card);
        });
    }

    async function loadSelectedHistory() {
        const runId = historySelect.value;
        if (!runId) return;
        activeRunId = runId;
        terminalContent.innerHTML = '';
        promptLine.textContent = `$ fwagent load ${runId}`;
        hdrTargetFw.textContent = runId;
        loadSummary(runId);
        appendLogLine(`Loaded past run artifacts for ${runId}`, 'log-stage');
    }

    async function replaySelectedHistory() {
        const runId = historySelect.value;
        if (!runId) return;
        activeRunId = runId;
        terminalContent.innerHTML = '';
        promptLine.textContent = `$ fwagent replay ${runId}`;
        hdrTargetFw.textContent = runId;
        resetStageTracker();
        connectSSE(`/api/runs/${runId}/replay`);
    }

    function showError(msg) {
        errorBannerText.textContent = msg;
        errorBanner.classList.remove('hidden');
    }

    function hideError() {
        errorBanner.classList.add('hidden');
    }

    function escapeHtml(str) {
        return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    }
});
