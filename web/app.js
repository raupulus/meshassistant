/**
 * Meshassistant · Dashboard Web 100% Offline
 * Lógica en JavaScript Vanilla para interacción WebSocket e IPC
 */

class MeshDashboard {
  constructor() {
    this.ws = null;
    this.reconnectTimer = null;
    this.nodesMap = new Map();
    this.messages = [];
    this.currentChannelFilter = 'all';
    this.currentNodeFilter = 'all';
    this.searchQuery = '';
    this.localNode = null;

    this.initElements();
    this.bindEvents();
    this.connectWebSocket();
  }

  initElements() {
    // LEDs y Status
    this.ledUart = document.getElementById('led-uart');
    this.lblUart = document.getElementById('lbl-uart');
    this.ledWs = document.getElementById('led-ws');
    this.lblWs = document.getElementById('lbl-ws');
    this.lblLocalNode = document.getElementById('lbl-local-node');
    this.lblChUtil = document.getElementById('lbl-ch-util');
    this.lblAirTx = document.getElementById('lbl-air-tx');

    // Conteo Badges
    this.countMsgs = document.getElementById('count-msgs');
    this.countRouters = document.getElementById('count-routers');
    this.countNodes = document.getElementById('count-nodes');

    // Contenedores
    this.chatFeed = document.getElementById('chat-feed');
    this.chatForm = document.getElementById('chat-form');
    this.chatText = document.getElementById('chat-text');
    this.chatDest = document.getElementById('chat-dest');
    this.routersGrid = document.getElementById('routers-grid');
    this.nodesTbody = document.getElementById('nodes-tbody');
    this.tracesGrid = document.getElementById('traces-grid');
    this.pollsContainer = document.getElementById('polls-container');
    this.weatherContent = document.getElementById('weather-content');
    this.weatherProvince = document.getElementById('weather-province');
    this.toastContainer = document.getElementById('toast-container');
  }

  bindEvents() {
    // Pestañas
    document.querySelectorAll('.tab-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const tab = btn.dataset.tab;
        this.switchTab(tab);
      });
    });

    // Filtros de Chat
    document.querySelectorAll('.filter-chip').forEach(chip => {
      chip.addEventListener('click', () => {
        document.querySelectorAll('.filter-chip').forEach(c => c.classList.remove('active'));
        chip.classList.add('active');
        this.currentChannelFilter = chip.dataset.ch;
        this.renderMessages();
      });
    });

    // Envío de Mensaje Chat
    this.chatForm.addEventListener('submit', (e) => {
      e.preventDefault();
      this.handleSendMessage();
    });

    // Búsqueda de Nodos
    const searchInput = document.getElementById('nodes-search');
    if (searchInput) {
      searchInput.addEventListener('input', (e) => {
        this.searchQuery = e.target.value.toLowerCase().trim();
        this.renderNodesTable();
      });
    }

    // Filtro de Nodos (Todos / RF / Favs)
    document.querySelectorAll('.filter-nodes').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.filter-nodes').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        this.currentNodeFilter = btn.dataset.filter;
        this.renderNodesTable();
      });
    });

    // Refrescar Routers
    const btnRefreshRouters = document.getElementById('btn-refresh-routers');
    if (btnRefreshRouters) {
      btnRefreshRouters.addEventListener('click', () => {
        this.sendAction('get_snapshot', { include: ['routers'] });
        this.showToast('Solicitando estado actualizado de repetidores...');
      });
    }

    // Formulario de Traceroute Manual
    const formTrace = document.getElementById('form-manual-trace');
    if (formTrace) {
      formTrace.addEventListener('submit', (e) => {
        e.preventDefault();
        const input = document.getElementById('trace-dest-input');
        const dest = input.value.trim();
        if (dest) {
          this.sendAction('request_trace', { dest: dest });
          this.showToast(`Traceroute encolado hacia ${dest}`);
          input.value = '';
        }
      });
    }
  }

  switchTab(tabName) {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));

    const activeBtn = document.querySelector(`.tab-btn[data-tab="${tabName}"]`);
    const activePane = document.getElementById(`pane-${tabName}`);
    if (activeBtn) activeBtn.classList.add('active');
    if (activePane) activePane.classList.add('active');
  }

  // ==========================================================================
  // Conexión WebSocket & Reconexión
  // ==========================================================================
  connectWebSocket() {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host || '127.0.0.1:8680';
    const wsUrl = `${protocol}//${host}`;

    this.setWsStatus(false, 'Conectando...');

    try {
      this.ws = new WebSocket(wsUrl);

      this.ws.onopen = () => {
        this.setWsStatus(true, 'Conectado');
        this.showToast('Conectado a la pasarela WebSocket');
      };

      this.ws.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          this.handleIncomingMessage(payload);
        } catch (err) {
          console.error('[WS Parse Error]', err, event.data);
        }
      };

      this.ws.onclose = () => {
        this.setWsStatus(false, 'Reconectando en 3s...');
        this.scheduleReconnect();
      };

      this.ws.onerror = () => {
        this.setWsStatus(false, 'Error');
        this.ws.close();
      };
    } catch (e) {
      this.setWsStatus(false, 'Fallo conexión');
      this.scheduleReconnect();
    }
  }

  scheduleReconnect() {
    if (!this.reconnectTimer) {
      this.reconnectTimer = setTimeout(() => this.connectWebSocket(), 3000);
    }
  }

  setWsStatus(online, text) {
    if (this.ledWs) {
      this.ledWs.className = `led ${online ? 'online' : 'offline'}`;
    }
    if (this.lblWs) {
      this.lblWs.textContent = text;
    }
  }

  setUartStatus(online, port) {
    if (this.ledUart) {
      this.ledUart.className = `led ${online ? 'online' : 'offline'}`;
    }
    if (this.lblUart) {
      this.lblUart.textContent = online ? `Activo (${port || 'UART'})` : 'Desconectado';
    }
  }

  // ==========================================================================
  // Despacho de Mensajes y Eventos
  // ==========================================================================
  handleIncomingMessage(payload) {
    // 1. Mensaje de bienvenida
    if (payload.event === 'welcome') {
      if (payload.data?.system_status) {
        this.setUartStatus(
          payload.data.system_status.uart_connected,
          payload.data.system_status.serial_port
        );
      }
      if (payload.data?.local_node) {
        this.localNode = payload.data.local_node;
        const name = this.localNode.short_name || this.localNode.my_node_id || 'Bot';
        if (this.lblLocalNode) this.lblLocalNode.textContent = name;
      }
      // Solicitar snapshot completo inicial
      this.sendAction('get_snapshot', {
        include: ['nodes', 'routers', 'recent_messages', 'stats', 'system_status', 'local_node', 'channel_metrics']
      });
      // Cargar encuestas y meteorología
      this.sendAction('get_polls');
      this.sendAction('get_weather');
      return;
    }

    // 2. Respuesta a una acción previa
    if (payload.type === 'response') {
      this.handleActionResponse(payload);
      return;
    }

    // 3. Eventos Push en tiempo real
    if (payload.event) {
      this.handlePushEvent(payload.event, payload.data, payload.ts);
    }
  }

  handlePushEvent(eventName, data, ts) {
    switch (eventName) {
      case 'message_rx':
        this.addMessage(data, ts);
        break;
      case 'system_status':
        this.setUartStatus(data.uart_connected, data.serial_port);
        break;
      case 'channel_metrics':
        if (this.lblChUtil && data.channel_util !== undefined) {
          this.lblChUtil.textContent = `${Number(data.channel_util).toFixed(1)}%`;
        }
        if (this.lblAirTx && data.air_util_tx !== undefined) {
          this.lblAirTx.textContent = `${Number(data.air_util_tx).toFixed(1)}%`;
        }
        break;
      case 'node_updated':
      case 'node_discovered':
        if (data && data.id) {
          this.nodesMap.set(data.id, { ...(this.nodesMap.get(data.id) || {}), ...data });
          this.renderNodesTable();
        }
        break;
      case 'device_telemetry':
        if (data && data.id && this.nodesMap.has(data.id)) {
          const n = this.nodesMap.get(data.id);
          n.battery = data.battery;
          n.voltage = data.voltage;
          this.renderNodesTable();
        }
        break;
      case 'trace_completed':
        this.renderTraceResult(data, ts);
        this.showToast(`Traceroute finalizado a ${data.to_name || data.to}`);
        break;
      case 'router_status':
        if (data.routers) {
          this.renderRouters(data.routers);
        }
        break;
      case 'poll_created':
        this.sendAction('get_polls');
        break;
      case 'message_ack':
        this.showToast(`Mensaje entregado con éxito a ${data.dest}`);
        break;
    }
  }

  handleActionResponse(resp) {
    if (!resp.success) {
      this.showToast(`Error: ${resp.error || 'Acción fallida'}`, 'danger');
      return;
    }

    const data = resp.data;
    if (!data) return;

    if (resp.action === 'get_snapshot') {
      if (data.recent_messages) {
        this.messages = [];
        data.recent_messages.forEach(m => {
          if (m.data) this.messages.push({ ...m.data, ts: m.ts });
        });
        this.renderMessages();
      }
      if (data.routers) {
        this.renderRouters(data.routers);
      }
      if (data.system_status) {
        this.setUartStatus(data.system_status.uart_connected, data.system_status.serial_port);
      }
      if (data.channel_metrics) {
        if (this.lblChUtil) this.lblChUtil.textContent = `${Number(data.channel_metrics.channel_util || 0).toFixed(1)}%`;
        if (this.lblAirTx) this.lblAirTx.textContent = `${Number(data.channel_metrics.air_util_tx || 0).toFixed(1)}%`;
      }
    } else if (resp.action === 'get_polls') {
      this.renderPolls(data.polls || []);
    } else if (resp.action === 'get_weather') {
      this.renderWeather(data);
    } else if (resp.action === 'set_node_favorite') {
      if (data.node_id && this.nodesMap.has(data.node_id)) {
        this.nodesMap.get(data.node_id).is_favorite = data.is_favorite;
        this.renderNodesTable();
      }
      this.showToast(`Nodo ${data.node_id} ${data.is_favorite ? 'añadido a favoritos' : 'desmarcado'}`);
    }
  }

  // ==========================================================================
  // Renderizado: Live Chat
  // ==========================================================================
  addMessage(msg, ts) {
    this.messages.push({ ...msg, ts: ts || new Date().toISOString() });
    if (this.messages.length > 50) this.messages.shift();
    this.renderMessages();
  }

  renderMessages() {
    if (!this.chatFeed) return;

    const filtered = this.messages.filter(m => {
      if (this.currentChannelFilter === 'all') return true;
      if (this.currentChannelFilter === '0') return m.channel === 0 && !m.is_direct;
      if (this.currentChannelFilter === 'direct') return m.is_direct;
      return true;
    });

    if (this.countMsgs) this.countMsgs.textContent = this.messages.length;

    if (filtered.length === 0) {
      this.chatFeed.innerHTML = `
        <div style="text-align: center; color: var(--text-dim); padding: 20px;">
          No hay mensajes en esta vista.
        </div>`;
      return;
    }

    this.chatFeed.innerHTML = filtered.map(m => {
      const senderName = m.from_name || m.from_short_name || m.from || 'Desconocido';
      const timeStr = m.ts ? m.ts.replace('T', ' ').substring(11, 19) : '--:--';
      const isDirect = m.is_direct;
      const channelBadge = isDirect 
        ? `<span class="badge badge-direct">Directo</span>`
        : `<span class="badge badge-ch0">Canal ${m.channel ?? 0}</span>`;
      const mqttBadge = m.via_mqtt ? `<span class="badge badge-mqtt">MQTT</span>` : '';
      const snrText = m.snr !== undefined ? `SNR: ${Number(m.snr).toFixed(1)}dB` : '';
      const hopsText = m.hops !== undefined ? `${m.hops} ${m.hops === 1 ? 'salto' : 'saltos'}` : '';

      return `
        <div class="msg-card">
          <div class="msg-header">
            <div style="display: flex; align-items: center; gap: 8px;">
              ${channelBadge}
              ${mqttBadge}
              <span class="msg-sender">${this.escapeHtml(senderName)}</span>
              <span style="font-size: 0.75rem; color: var(--text-dim);">${this.escapeHtml(m.from || '')}</span>
            </div>
            <span class="msg-meta">${timeStr}</span>
          </div>
          <div class="msg-body">${this.escapeHtml(m.text || '')}</div>
          <div class="msg-footer">
            ${snrText ? `<span>${snrText}</span>` : ''}
            ${hopsText ? `<span>• ${hopsText}</span>` : ''}
          </div>
        </div>
      `;
    }).join('');

    this.chatFeed.scrollTop = this.chatFeed.scrollHeight;
  }

  handleSendMessage() {
    const text = this.chatText.value.trim();
    if (!text) return;

    const destValue = this.chatDest.value;
    let dest = '^all';
    let channel = 0;

    if (destValue.startsWith('^all:')) {
      channel = parseInt(destValue.split(':')[1], 10) || 0;
      dest = '^all';
    } else {
      dest = destValue;
    }

    this.sendAction('send_message', {
      text: text,
      dest: dest,
      channel: channel,
    });

    this.chatText.value = '';
    this.showToast('Mensaje enviado a la cola de emisión');
  }

  // ==========================================================================
  // Renderizado: Routers
  // ==========================================================================
  renderRouters(routers) {
    if (!this.routersGrid) return;
    if (this.countRouters) this.countRouters.textContent = routers.length;

    if (routers.length === 0) {
      this.routersGrid.innerHTML = `<div style="color: var(--text-dim);">No hay routers configurados en env.ROUTER_NODES.</div>`;
      return;
    }

    this.routersGrid.innerHTML = routers.map(r => {
      const isOnline = r.status === 'online';
      const snr = r.snr !== undefined && r.snr !== null ? `${Number(r.snr).toFixed(1)} dB` : '--';
      const lastSeen = r.last_seen_sec !== undefined ? `${Math.round(r.last_seen_sec / 60)} min` : '--';

      return `
        <div class="card">
          <div class="card-header">
            <span>${this.escapeHtml(r.name || r.id)}</span>
            <span class="badge" style="background: ${isOnline ? 'var(--success-bg)' : 'var(--danger-bg)'}; color: ${isOnline ? 'var(--success)' : 'var(--danger)'};">
              ${isOnline ? 'ONLINE' : 'OFFLINE'}
            </span>
          </div>
          <div class="card-row">
            <span>ID Hex:</span>
            <span>${this.escapeHtml(r.id)}</span>
          </div>
          <div class="card-row">
            <span>SNR Medio:</span>
            <span>${snr}</span>
          </div>
          <div class="card-row">
            <span>Último visto hace:</span>
            <span>${lastSeen}</span>
          </div>
          <button class="btn-secondary" style="margin-top: 6px; width: 100%; font-weight: 600;" onclick="window.dashboard.requestTraceTo('${r.id}')">
            📍 Lanzar Traceroute
          </button>
        </div>
      `;
    }).join('');
  }

  requestTraceTo(nodeId) {
    this.sendAction('request_trace', { dest: nodeId });
    this.showToast(`Traceroute encolado hacia ${nodeId}`);
  }

  // ==========================================================================
  // Renderizado: Nodos
  // ==========================================================================
  renderNodesTable() {
    if (!this.nodesTbody) return;

    let nodes = Array.from(this.nodesMap.values());
    if (this.countNodes) this.countNodes.textContent = nodes.length;

    // Filtro texto
    if (this.searchQuery) {
      nodes = nodes.filter(n => {
        const id = (n.id || '').toLowerCase();
        const name = (n.name || '').toLowerCase();
        const short = (n.short_name || '').toLowerCase();
        return id.includes(this.searchQuery) || name.includes(this.searchQuery) || short.includes(this.searchQuery);
      });
    }

    // Filtro categoría
    if (this.currentNodeFilter === 'rf') {
      nodes = nodes.filter(n => !n.via_mqtt);
    } else if (this.currentNodeFilter === 'fav') {
      nodes = nodes.filter(n => n.is_favorite);
    }

    if (nodes.length === 0) {
      this.nodesTbody.innerHTML = `
        <tr>
          <td colspan="8" style="text-align: center; color: var(--text-dim); padding: 20px;">
            No se encontraron nodos con los filtros aplicados.
          </td>
        </tr>`;
      return;
    }

    this.nodesTbody.innerHTML = nodes.map(n => {
      const isFav = !!n.is_favorite;
      const battery = n.battery !== undefined ? `${n.battery}%` : '--';
      const snr = n.snr !== undefined ? `${Number(n.snr).toFixed(1)} dB` : '--';
      const hops = n.hops !== undefined ? n.hops : '--';

      return `
        <tr>
          <td>
            <button class="star-btn ${isFav ? 'fav' : ''}" onclick="window.dashboard.toggleFavorite('${n.id}', ${!isFav})">
              ★
            </button>
          </td>
          <td>
            <strong>${this.escapeHtml(n.name || n.short_name || 'Sin nombre')}</strong>
            ${n.short_name ? `<div style="font-size: 0.75rem; color: var(--text-muted);">${this.escapeHtml(n.short_name)}</div>` : ''}
          </td>
          <td style="font-family: monospace; font-size: 0.85rem;">${this.escapeHtml(n.id || '')}</td>
          <td><span class="badge" style="background: var(--primary-bg); color: var(--primary);">${this.escapeHtml(n.role_name || 'CLIENT')}</span></td>
          <td>${snr}</td>
          <td>${hops}</td>
          <td>${battery}</td>
          <td>
            <button class="btn-secondary" style="padding: 3px 8px; font-size: 0.75rem;" onclick="window.dashboard.requestTraceTo('${n.id}')">
              Trace
            </button>
          </td>
        </tr>
      `;
    }).join('');
  }

  toggleFavorite(nodeId, makeFav) {
    this.sendAction('set_node_favorite', { node_id: nodeId, is_favorite: makeFav });
  }

  // ==========================================================================
  // Renderizado: Traceroutes
  // ==========================================================================
  renderTraceResult(trace, ts) {
    if (!this.tracesGrid) return;

    const timeStr = ts ? ts.replace('T', ' ').substring(0, 19) : new Date().toLocaleString();
    const hopsFwd = trace.hops_forward || [];
    const hopsBwd = trace.hops_backward || [];

    const fwdStr = hopsFwd.length > 0 
      ? hopsFwd.map(h => `${this.escapeHtml(h.name || h.id)} (${h.snr !== undefined ? h.snr + 'dB' : ''})`).join(' ➔ ')
      : 'Directo / Sin repetidores intermedios';

    const cardHtml = `
      <div class="card" style="border-left: 4px solid var(--primary);">
        <div class="card-header">
          <span>Destino: ${this.escapeHtml(trace.to_name || trace.to)}</span>
          <span class="badge" style="background: ${trace.success ? 'var(--success-bg)' : 'var(--danger-bg)'}; color: ${trace.success ? 'var(--success)' : 'var(--danger)'};">
            ${trace.success ? 'ÉXITO' : 'FALLIDO'}
          </span>
        </div>
        <div class="card-row">
          <span>Fecha/Hora:</span>
          <span>${timeStr}</span>
        </div>
        <div style="margin-top: 6px; font-size: 0.85rem;">
          <strong style="color: var(--primary);">Ruta de Ida:</strong>
          <div style="background: var(--bg-main); padding: 6px 10px; border-radius: var(--radius-sm); margin-top: 4px; font-family: monospace; font-size: 0.8rem;">
            ${fwdStr}
          </div>
        </div>
        ${trace.raw_text ? `
          <div style="font-size: 0.75rem; color: var(--text-dim); margin-top: 4px;">
            ${this.escapeHtml(trace.raw_text)}
          </div>` : ''}
      </div>
    `;

    if (this.tracesGrid.innerHTML.includes('No hay traceroutes')) {
      this.tracesGrid.innerHTML = cardHtml;
    } else {
      this.tracesGrid.insertAdjacentHTML('afterbegin', cardHtml);
    }
  }

  // ==========================================================================
  // Renderizado: Encuestas & Clima
  // ==========================================================================
  renderPolls(polls) {
    if (!this.pollsContainer) return;

    if (polls.length === 0) {
      this.pollsContainer.innerHTML = `<div style="color: var(--text-dim);">No hay encuestas comunitarias activas.</div>`;
      return;
    }

    this.pollsContainer.innerHTML = polls.map(p => {
      const options = p.options || [];
      const counts = p.counts || [];
      const total = p.total_votes || 1;

      const optionsHtml = options.map((opt, idx) => {
        const votes = counts[idx] || 0;
        const pct = Math.round((votes / (total || 1)) * 100);
        return `
          <div style="margin-bottom: 8px;">
            <div style="display: flex; justify-content: space-between; font-size: 0.85rem; margin-bottom: 4px;">
              <span>${this.escapeHtml(opt)}</span>
              <span><strong>${votes}</strong> votos (${pct}%)</span>
            </div>
            <div style="background: var(--bg-main); height: 8px; border-radius: 4px; overflow: hidden;">
              <div style="background: var(--primary); width: ${pct}%; height: 100%;"></div>
            </div>
            <button class="btn-secondary" style="margin-top: 4px; padding: 2px 8px; font-size: 0.75rem;" onclick="window.dashboard.votePoll(${p.id}, ${idx})">
              Votar esta opción
            </button>
          </div>
        `;
      }).join('');

      return `
        <div class="card">
          <div class="card-header">
            <span>${this.escapeHtml(p.question || 'Encuesta')}</span>
            <span class="badge" style="background: var(--primary-bg); color: var(--primary);">ID #${p.id}</span>
          </div>
          <div style="margin-top: 8px;">${optionsHtml}</div>
        </div>
      `;
    }).join('');
  }

  votePoll(pollId, optIdx) {
    this.sendAction('vote_poll', {
      poll_id: pollId,
      option_index: optIdx,
      node_id: this.localNode?.my_node_id || 'web_client'
    });
    this.showToast(`Voto registrado en la encuesta #${pollId}`);
    setTimeout(() => this.sendAction('get_polls'), 500);
  }

  renderWeather(data) {
    if (this.weatherProvince) {
      this.weatherProvince.textContent = `Predicción: ${data.province || 'Cádiz'}`;
    }
    if (this.weatherContent) {
      this.weatherContent.textContent = data.content || 'Sin datos de predicción meteorológica disponibles.';
    }
  }

  // ==========================================================================
  // Enviar Acciones por WebSocket
  // ==========================================================================
  sendAction(actionName, params = {}) {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      this.showToast('No hay conexión con el servidor WebSocket', 'danger');
      return;
    }

    const payload = {
      action: actionName,
      req_id: `req_${Date.now()}_${Math.floor(Math.random() * 1000)}`,
      params: params
    };

    this.ws.send(JSON.stringify(payload));
  }

  // ==========================================================================
  // Utilidades
  // ==========================================================================
  showToast(message, type = 'info') {
    if (!this.toastContainer) return;
    const toast = document.createElement('div');
    toast.className = 'toast';
    if (type === 'danger') {
      toast.style.borderColor = 'var(--danger)';
      toast.style.color = 'var(--danger)';
    } else {
      toast.style.borderColor = 'var(--primary)';
    }
    toast.textContent = message;
    this.toastContainer.appendChild(toast);
    setTimeout(() => toast.remove(), 4000);
  }

  escapeHtml(text) {
    if (!text) return '';
    return String(text)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }
}

// Iniciar aplicación al cargar el DOM
window.addEventListener('DOMContentLoaded', () => {
  window.dashboard = new MeshDashboard();
});
