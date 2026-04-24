const TYPE_COLORS = {
    PERSON: '#c95b38',
    ORG: '#1d7f77',
    GPE: '#4d8a4f',
    LOC: '#2f7c64',
    DATE: '#d7a63c',
    EVENT: '#9b4f7d',
    WORK_OF_ART: '#ae6831',
    FAC: '#3286a8',
    NORP: '#7c7a63',
    LAW: '#42516f',
    LANGUAGE: '#3c8e81',
    PRODUCT: '#9d5621',
    CONCEPT: '#7a5db8',
    DEVICE: '#a63f33',
    AWARD: '#b9891a',
    UNKNOWN: '#98a39d'
};

const RELATION_COLORS = [
    '#c95b38',
    '#1d7f77',
    '#4d8a4f',
    '#9b4f7d',
    '#ae6831',
    '#42516f',
    '#d7a63c',
    '#7a5db8',
    '#3286a8',
    '#8e6c35',
    '#7b5f52',
    '#2f7c64'
];

const state = {
    network: null,
    fullGraph: null,
    currentGraph: null,
    currentNodeId: null,
    activeTaskId: null,
    taskPollHandle: null,
    ui: {
        leftCollapsed: false,
        rightCollapsed: false
    }
};

document.addEventListener('DOMContentLoaded', async () => {
    bindEvents();
    await Promise.all([
        loadSummary(),
        loadScripts(),
        loadDownloads(),
        loadFullGraph()
    ]);
});

function bindEvents() {
    document.getElementById('queryForm').addEventListener('submit', onQuerySubmit);
    document.getElementById('showFullGraphBtn').addEventListener('click', () => {
        if (state.fullGraph) {
            renderGraph(state.fullGraph, '完整图谱');
            document.getElementById('detailStatus').textContent = '完整图谱视图';
        }
    });
    document.getElementById('reloadGraphBtn').addEventListener('click', reloadGraphFromServer);
    document.getElementById('downloadCurrentPngBtn').addEventListener('click', downloadCurrentViewPng);
    document.getElementById('toggleControlsBtn').addEventListener('click', () => toggleSidebar('left'));
    document.getElementById('graphToggleControlsBtn').addEventListener('click', () => toggleSidebar('left'));
    document.getElementById('toggleDetailsBtn').addEventListener('click', () => toggleSidebar('right'));
    document.getElementById('graphToggleDetailsBtn').addEventListener('click', () => toggleSidebar('right'));
    window.addEventListener('resize', () => refreshNetworkViewport(false));
    applyWorkspaceLayout();
}

function toggleSidebar(side) {
    if (side === 'left') {
        state.ui.leftCollapsed = !state.ui.leftCollapsed;
    } else {
        state.ui.rightCollapsed = !state.ui.rightCollapsed;
    }
    applyWorkspaceLayout();
    window.setTimeout(() => refreshNetworkViewport(true), 180);
}

function applyWorkspaceLayout() {
    const workspace = document.getElementById('workspace');
    workspace.classList.toggle('left-collapsed', state.ui.leftCollapsed);
    workspace.classList.toggle('right-collapsed', state.ui.rightCollapsed);
    syncSidebarButtons(
        ['toggleControlsBtn', 'graphToggleControlsBtn'],
        state.ui.leftCollapsed,
        '折叠左栏',
        '展开左栏'
    );
    syncSidebarButtons(
        ['toggleDetailsBtn', 'graphToggleDetailsBtn'],
        state.ui.rightCollapsed,
        '折叠右栏',
        '展开右栏'
    );
}

function syncSidebarButtons(ids, collapsed, expandedLabel, collapsedLabel) {
    for (const id of ids) {
        const button = document.getElementById(id);
        if (!button) {
            continue;
        }
        button.textContent = collapsed ? collapsedLabel : expandedLabel;
        button.setAttribute('aria-pressed', String(collapsed));
    }
}

function refreshNetworkViewport(shouldFit) {
    if (!state.network) {
        return;
    }
    requestAnimationFrame(() => {
        state.network.redraw();
        if (shouldFit) {
            state.network.fit({
                animation: {
                    duration: 280,
                    easingFunction: 'easeInOutQuad'
                }
            });
        }
    });
}

async function apiFetch(url, options = {}) {
    const response = await fetch(url, options);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
        throw new Error(data.error || `请求失败: ${response.status}`);
    }
    return data;
}

async function loadSummary() {
    const summary = await apiFetch('/api/graph/summary');
    const container = document.getElementById('summaryCards');
    container.innerHTML = '';

    const cards = [
        ['节点数', summary.num_nodes],
        ['边数', summary.num_edges],
        ['主类型', summary.top_node_types?.[0]?.type || 'N/A'],
        ['主关系', summary.top_relations?.[0]?.relation || 'N/A']
    ];

    for (const [label, value] of cards) {
        const card = document.createElement('div');
        card.className = 'summary-card';
        card.innerHTML = `<div class="label">${escapeHtml(label)}</div><div class="value">${escapeHtml(String(value))}</div>`;
        container.appendChild(card);
    }
}

async function loadFullGraph() {
    state.fullGraph = await apiFetch('/api/graph/full');
    renderGraph(state.fullGraph, '完整图谱');
}

async function reloadGraphFromServer() {
    const button = document.getElementById('reloadGraphBtn');
    button.disabled = true;
    button.textContent = '重载中...';
    try {
        await apiFetch('/api/graph/reload', { method: 'POST' });
        await loadSummary();
        await loadFullGraph();
        setQueryStatus('图谱已重载');
    } catch (error) {
        setQueryStatus(error.message);
    } finally {
        button.disabled = false;
        button.textContent = '重载图谱';
    }
}

function renderGraph(payload, caption) {
    state.currentGraph = payload;
    document.getElementById('graphCaption').textContent = `${caption} · ${payload.stats?.num_nodes || 0} 个节点 / ${payload.stats?.num_edges || 0} 条边`;
    const container = document.getElementById('networkCanvas');

    const nodes = new vis.DataSet((payload.nodes || []).map(node => ({
        id: node.id,
        label: node.label,
        title: buildNodeTooltip(node),
        color: node.is_center
            ? { background: '#1d2a26', border: '#c95b38', highlight: { background: '#1d2a26', border: '#c95b38' } }
            : TYPE_COLORS[node.type] || TYPE_COLORS.UNKNOWN,
        size: 18 + Math.min((node.degree || 0) * 2.4, 30),
        font: { color: node.is_center ? '#fff7ef' : '#26332f', face: 'Georgia' },
        borderWidth: node.is_center ? 3 : 1.5,
        shape: 'dot'
    })));

    const edges = new vis.DataSet((payload.edges || []).map(edge => {
        const relationColor = getRelationColor(edge.relation);
        return {
            id: `${edge.source}::${edge.relation}::${edge.target}`,
            from: edge.source,
            to: edge.target,
            label: edge.relation,
            title: buildEdgeTooltip(edge),
            arrows: 'to',
            width: 1.4 + Number(edge.confidence || 0) * 1.3,
            color: { color: relationColor, highlight: relationColor, hover: relationColor, opacity: 0.82 },
            font: { color: relationColor, size: 11, strokeWidth: 3, strokeColor: 'rgba(255, 250, 242, 0.88)' },
            smooth: { type: 'dynamic', roundness: 0.22 }
        };
    }));

    const data = { nodes, edges };
    const options = {
        autoResize: true,
        interaction: { hover: true, tooltipDelay: 120, multiselect: false },
        physics: {
            stabilization: { iterations: 180 },
            forceAtlas2Based: {
                gravitationalConstant: -68,
                centralGravity: 0.015,
                springLength: 175,
                springConstant: 0.055,
                damping: 0.48
            },
            solver: 'forceAtlas2Based'
        },
        edges: { smooth: false, selectionWidth: width => width + 1.8 },
        nodes: { shadow: { enabled: true, color: 'rgba(0,0,0,0.08)', size: 12, x: 0, y: 6 } }
    };

    if (state.network) {
        state.network.destroy();
    }

    state.network = new vis.Network(container, data, options);
    state.network.once('stabilizationIterationsDone', () => refreshNetworkViewport(true));
    state.network.on('click', params => {
        if (params.nodes.length) {
            loadNodeDetails(params.nodes[0]);
        }
    });
}

async function onQuerySubmit(event) {
    event.preventDefault();
    const keyword = document.getElementById('keywordInput').value.trim();
    const limit = Number(document.getElementById('limitInput').value || 8);
    const radius = Number(document.getElementById('radiusInput').value || 1);

    if (!keyword) {
        setQueryStatus('请输入关键词');
        return;
    }

    setQueryStatus('查询中...');
    try {
        const payload = await apiFetch(`/api/query?keyword=${encodeURIComponent(keyword)}&limit=${limit}&radius=${radius}`);
        renderQueryResults(payload.matches || []);
        if (payload.primary) {
            state.currentNodeId = payload.primary.node.id;
            renderNodeDetails(payload.primary);
            renderGraph(payload.subgraph, `关键词：${keyword}`);
            setQueryStatus(`命中 ${payload.matches.length} 个节点，当前展示 ${payload.primary.node.label}`);
        } else {
            renderEmptyDetails('没有匹配到任何节点。');
            renderGraph({ nodes: [], edges: [], stats: { num_nodes: 0, num_edges: 0 } }, `关键词：${keyword}`);
            setQueryStatus('未找到匹配节点');
        }
    } catch (error) {
        setQueryStatus(error.message);
    }
}

function renderQueryResults(matches) {
    const container = document.getElementById('queryResults');
    container.innerHTML = '';
    if (!matches.length) {
        container.className = 'result-list empty-state';
        container.textContent = '未找到匹配节点。';
        return;
    }

    container.className = 'result-list';
    for (const match of matches) {
        const item = document.createElement('button');
        item.type = 'button';
        item.className = 'result-item';
        item.innerHTML = `
      <div class="result-item-header">
        <div>
          <strong>${escapeHtml(match.label)}</strong>
          <div class="meta-row">
            <span class="pill">${escapeHtml(match.type || 'UNKNOWN')}</span>
            <span>度数 ${match.degree}</span>
          </div>
        </div>
        <span class="pill score-pill">得分 ${match.score}</span>
      </div>
      ${match.description ? `<p class="muted-text">${escapeHtml(match.description)}</p>` : ''}
    `;
        item.addEventListener('click', () => loadNodeDetails(match.id));
        container.appendChild(item);
    }
}

async function loadNodeDetails(nodeId) {
    const radius = Number(document.getElementById('radiusInput').value || 1);
    try {
        const payload = await apiFetch(`/api/node/${encodeURIComponent(nodeId)}?radius=${radius}`);
        state.currentNodeId = payload.details.node.id;
        renderNodeDetails(payload.details);
        renderGraph(payload.subgraph, `节点：${payload.details.node.label}`);
        highlightActiveResult(payload.details.node.id);
    } catch (error) {
        renderEmptyDetails(error.message);
    }
}

function renderNodeDetails(details) {
    const container = document.getElementById('nodeDetail');
    container.className = 'node-detail';
    document.getElementById('detailStatus').textContent = details.node.label;

    const neighborCards = (details.neighbors || []).slice(0, 10).map(neighbor => `
    <div class="neighbor-card">
      <div class="neighbor-card-header">
        <div>
          <button class="inline-button" type="button" data-node-id="${escapeHtml(neighbor.id)}">${escapeHtml(neighbor.label)}</button>
          <div class="meta-row">
            <span class="pill">${escapeHtml(neighbor.type || 'UNKNOWN')}</span>
            <span>度数 ${neighbor.degree}</span>
            <span>关联 ${neighbor.relation_count}</span>
          </div>
        </div>
      </div>
      ${neighbor.description ? `<p class="muted-text">${escapeHtml(neighbor.description)}</p>` : ''}
    </div>
  `).join('');

    container.innerHTML = `
    <div class="detail-grid">
      <div class="detail-card">
        <h3>${escapeHtml(details.node.label)}</h3>
        <div class="meta-row">
          <span class="pill">${escapeHtml(details.node.type || 'UNKNOWN')}</span>
          <span>入度 ${details.node.in_degree}</span>
          <span>出度 ${details.node.out_degree}</span>
          <span>总度数 ${details.node.degree}</span>
        </div>
        ${details.node.wikidata_qid ? `<p class="muted-text">QID: ${escapeHtml(details.node.wikidata_qid)}</p>` : ''}
        ${details.node.description ? `<p>${escapeHtml(details.node.description)}</p>` : '<p class="muted-text">该节点暂无描述信息。</p>'}
      </div>

      <div class="detail-card">
        <h4>出边关系</h4>
        ${renderRelationList(details.outgoing, 'target')}
      </div>

      <div class="detail-card">
        <h4>入边关系</h4>
        ${renderRelationList(details.incoming, 'source')}
      </div>

      <div class="detail-card">
        <h4>相关节点</h4>
        <div class="node-detail">${neighborCards || '<div class="empty-state">暂无相关节点。</div>'}</div>
      </div>
    </div>
  `;

    container.querySelectorAll('[data-node-id]').forEach(button => {
        button.addEventListener('click', () => loadNodeDetails(button.dataset.nodeId));
    });
}

function renderRelationList(rows, keyField) {
    if (!rows || !rows.length) {
        return '<div class="empty-state">暂无关系。</div>';
    }
    const items = rows.slice(0, 12).map(row => `
    <li>
      <strong>${escapeHtml(row.relation || 'unknown')}</strong>
      <span> → ${escapeHtml(row[keyField])}</span>
      ${row.provenance ? `<span class="muted-text"> · ${escapeHtml(row.provenance)}</span>` : ''}
    </li>
  `).join('');
    return `<ul class="relation-list">${items}</ul>`;
}

function renderEmptyDetails(message) {
    const container = document.getElementById('nodeDetail');
    container.className = 'node-detail empty-state';
    container.textContent = message;
    document.getElementById('detailStatus').textContent = '未选择节点';
}

function highlightActiveResult(nodeId) {
    document.querySelectorAll('.result-item').forEach(item => item.classList.remove('active'));
    document.querySelectorAll('.result-item').forEach(item => {
        if (item.textContent.includes(nodeId)) {
            item.classList.add('active');
        }
    });
}

async function loadScripts() {
    const payload = await apiFetch('/api/scripts');
    const container = document.getElementById('scriptList');
    container.innerHTML = '';
    container.className = 'script-list';

    for (const script of payload.scripts || []) {
        const card = document.createElement('div');
        card.className = 'script-card';
        card.innerHTML = `
      <div class="subsection-header compact">
        <div>
          <strong>${escapeHtml(script.label)}</strong>
          <p class="muted-text">${escapeHtml(script.description)}</p>
        </div>
        <button class="script-run-button" type="button">运行</button>
      </div>
      <div class="meta-row"><span>${escapeHtml(script.command_preview)}</span></div>
    `;
        card.querySelector('button').addEventListener('click', () => startScriptTask(script.id));
        container.appendChild(card);
    }
}

async function startScriptTask(scriptId) {
    const response = await apiFetch('/api/scripts/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ script_id: scriptId })
    });
    state.activeTaskId = response.task_id;
    updateTaskUI(response);
    pollTask(state.activeTaskId);
}

async function pollTask(taskId) {
    if (state.taskPollHandle) {
        clearInterval(state.taskPollHandle);
    }

    state.taskPollHandle = setInterval(async () => {
        try {
            const task = await apiFetch(`/api/tasks/${taskId}`);
            updateTaskUI(task);
            if (task.status === 'completed' || task.status === 'failed') {
                clearInterval(state.taskPollHandle);
                state.taskPollHandle = null;
                await loadSummary();
                await loadDownloads();
                if (task.status === 'completed') {
                    await loadFullGraph();
                }
            }
        } catch (error) {
            updateTaskStatus(error.message);
            clearInterval(state.taskPollHandle);
            state.taskPollHandle = null;
        }
    }, 1800);
}

function updateTaskUI(task) {
    updateTaskStatus(`${task.label} · ${task.status}`);
    document.getElementById('taskLog').textContent = task.output || '任务已提交，等待输出...';
}

function updateTaskStatus(text) {
    document.getElementById('taskStatus').textContent = text;
}

async function loadDownloads() {
    const payload = await apiFetch('/api/downloads');
    const container = document.getElementById('downloadList');
    container.innerHTML = '';
    container.className = 'download-list';

    for (const item of payload.downloads || []) {
        const card = document.createElement('div');
        card.className = 'download-card';
        card.innerHTML = `
      <div class="download-card-header">
        <div>
          <strong>${escapeHtml(item.label)}</strong>
          <div class="meta-row"><span>${item.available ? '可下载' : '当前不存在'}</span></div>
        </div>
        <a class="download-link" ${item.available ? `href="/api/download/${encodeURIComponent(item.id)}"` : ''} ${item.available ? '' : 'aria-disabled="true"'}>
          下载
        </a>
      </div>
    `;
        if (!item.available) {
            card.querySelector('a').addEventListener('click', event => event.preventDefault());
            card.querySelector('a').style.opacity = '0.45';
            card.querySelector('a').style.pointerEvents = 'none';
        }
        container.appendChild(card);
    }
}

function downloadCurrentViewPng() {
    if (!state.network || !state.network.canvas || !state.network.canvas.frame) {
        setQueryStatus('当前没有可导出的图谱视图');
        return;
    }

    const canvas = state.network.canvas.frame.canvas;
    const url = canvas.toDataURL('image/png');
    const link = document.createElement('a');
    link.href = url;
    link.download = `kg-turing-view-${Date.now()}.png`;
    link.click();
}

function setQueryStatus(text) {
    document.getElementById('queryStatus').textContent = text;
}

function buildNodeTooltip(node) {
    return `
    <div>
      <strong>${escapeHtml(node.label)}</strong><br>
      类型: ${escapeHtml(node.type || 'UNKNOWN')}<br>
      度数: ${node.degree || 0}
      ${node.wikidata_qid ? `<br>QID: ${escapeHtml(node.wikidata_qid)}` : ''}
      ${node.description ? `<br>${escapeHtml(node.description)}` : ''}
    </div>
  `;
}

function buildEdgeTooltip(edge) {
    return `
    <div>
      <strong>${escapeHtml(edge.relation || 'unknown')}</strong><br>
      ${escapeHtml(edge.source)} → ${escapeHtml(edge.target)}<br>
      置信度: ${Number(edge.confidence || 0).toFixed(2)}
      ${edge.provenance ? `<br>来源: ${escapeHtml(edge.provenance)}` : ''}
    </div>
  `;
}

function getRelationColor(relation) {
    const normalized = String(relation || 'unknown').trim().toLowerCase();
    let hash = 0;
    for (let index = 0; index < normalized.length; index += 1) {
        hash = (hash + (index + 1) * normalized.charCodeAt(index)) >>> 0;
    }
    return RELATION_COLORS[hash % RELATION_COLORS.length];
}

function escapeHtml(value) {
    return String(value)
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;');
}