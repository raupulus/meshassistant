/**
 * Meshassistant · Dashboard Web 100% Offline
 * Lógica en JavaScript Vanilla para interacción WebSocket e IPC
 */

class MeshDashboard {
  constructor() {
    this.ws = null;
    this.reconnectTimer = null;
    this.syncInterval = null;
    this.nodesMap = new Map();
    this.messages = [];
    this.channels = {};
    this.currentChannelFilter = "all";
    this.currentNodeFilter = "all";
    this.currentRoleFilter = "all";
    this.sortField = "is_favorite";
    this.sortDirection = "desc";
    this.searchQuery = "";
    this.localNode = null;
    this.auditHours = 24;
    this.auditLimit = 100;
    this.auditOffset = 0;
    this.auditPage = 1;
    this.auditData = null;
    this.auditSearchQuery = "";

    this.initElements();
    this.bindEvents();
    this.connectWebSocket();
  }

  initElements() {
    // LEDs y Status
    this.ledUart = document.getElementById("led-uart");
    this.lblUart = document.getElementById("lbl-uart");
    this.ledWs = document.getElementById("led-ws");
    this.lblWs = document.getElementById("lbl-ws");
    this.lblLocalNode = document.getElementById("lbl-local-node");
    this.lblChUtil = document.getElementById("lbl-ch-util");
    this.lblAirTx = document.getElementById("lbl-air-tx");

    // Conteo Badges
    this.countMsgs = document.getElementById("count-msgs");
    this.countRouters = document.getElementById("count-routers");
    this.countNodes = document.getElementById("count-nodes");

    // Contenedores
    this.chatFeed = document.getElementById("chat-feed");
    this.chatForm = document.getElementById("chat-form");
    this.chatText = document.getElementById("chat-text");
    this.chatDest = document.getElementById("chat-dest");
    this.routersGrid = document.getElementById("routers-grid");
    this.nodesTbody = document.getElementById("nodes-tbody");
    this.tracesGrid = document.getElementById("traces-grid");
    this.pollsContainer = document.getElementById("polls-container");
    this.weatherContent = document.getElementById("weather-content");
    this.weatherProvince = document.getElementById("weather-province");
    this.toastContainer = document.getElementById("toast-container");

    // Elementos de Auditoría
    this.auditTotalCmds = document.getElementById("audit-total-cmds");
    this.auditTotalPeriod = document.getElementById("audit-total-period");
    this.auditUniqueNodes = document.getElementById("audit-unique-nodes");
    this.auditTopCommand = document.getElementById("audit-top-command");
    this.auditTopCommandCount = document.getElementById("audit-top-command-count");
    this.auditTopUser = document.getElementById("audit-top-user");
    this.auditTopUserCount = document.getElementById("audit-top-user-count");
    this.auditRankingTbody = document.getElementById("audit-ranking-tbody");
    this.auditLogsTbody = document.getElementById("audit-logs-tbody");
    this.auditLogsSearch = document.getElementById("audit-logs-search");
    this.btnAuditPrev = document.getElementById("btn-audit-prev");
    this.btnAuditNext = document.getElementById("btn-audit-next");
    this.lblAuditPage = document.getElementById("lbl-audit-page");
  }

  bindEvents() {
    // Pestañas
    document.querySelectorAll(".tab-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        const tab = btn.dataset.tab;
        this.switchTab(tab);
      });
    });

    // Envío de Mensaje Chat
    if (this.chatForm) {
      this.chatForm.addEventListener("submit", (e) => {
        e.preventDefault();
        this.handleSendMessage();
      });
    }

    // Búsqueda de Nodos
    const searchInput = document.getElementById("nodes-search");
    if (searchInput) {
      searchInput.addEventListener("input", (e) => {
        this.searchQuery = e.target.value.toLowerCase().trim();
        this.renderNodesTable();
      });
    }

    // Filtro por Rol en Nodos
    const roleFilter = document.getElementById("nodes-role-filter");
    if (roleFilter) {
      roleFilter.addEventListener("change", (e) => {
        this.currentRoleFilter = e.target.value;
        this.renderNodesTable();
      });
    }

    // Filtro de Nodos (Todos / RF / Favs)
    document.querySelectorAll(".filter-nodes").forEach(btn => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".filter-nodes").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        this.currentNodeFilter = btn.dataset.filter;
        this.renderNodesTable();
      });
    });

    // Ordenación de columnas de la tabla de Nodos
    document.querySelectorAll(".sort-header").forEach(th => {
      th.addEventListener("click", () => {
        const field = th.dataset.sort;
        if (!field) return;
        if (this.sortField === field) {
          this.sortDirection = this.sortDirection === "asc" ? "desc" : "asc";
        } else {
          this.sortField = field;
          this.sortDirection = (field === "is_favorite" || field === "battery" || field === "snr" || field === "last_heard" || field === "created_at") ? "desc" : "asc";
        }
        this.updateSortHeaders();
        this.renderNodesTable();
      });
    });

    // Refrescar Routers
    const btnRefreshRouters = document.getElementById("btn-refresh-routers");
    if (btnRefreshRouters) {
      btnRefreshRouters.addEventListener("click", () => {
        this.sendAction("get_snapshot", { include: ["routers"] });
        this.showToast("Solicitando estado actualizado de repetidores...");
      });
    }

    // Formulario de Traceroute Manual
    const formTrace = document.getElementById("form-manual-trace");
    if (formTrace) {
      formTrace.addEventListener("submit", (e) => {
        e.preventDefault();
        const input = document.getElementById("trace-dest-input");
        const dest = input.value.trim();
        if (dest) {
          this.sendAction("request_trace", { dest: dest });
          this.showToast(`Traceroute encolado hacia ${dest}`);
          input.value = "";
        }
      });
    }

    // Filtros de Periodo en Auditoría
    document.querySelectorAll(".filter-audit-period").forEach(btn => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".filter-audit-period").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        const h = btn.dataset.hours;
        this.auditHours = h === "all" ? null : parseInt(h, 10);
        this.auditOffset = 0;
        this.auditPage = 1;
        this.loadAuditData();
      });
    });

    // Buscador en Logs de Auditoría
    if (this.auditLogsSearch) {
      this.auditLogsSearch.addEventListener("input", (e) => {
        this.auditSearchQuery = e.target.value.toLowerCase().trim();
        this.renderAuditLogs();
      });
    }

    // Paginación en Logs de Auditoría
    if (this.btnAuditPrev) {
      this.btnAuditPrev.addEventListener("click", () => {
        if (this.auditOffset >= this.auditLimit) {
          this.auditOffset -= this.auditLimit;
          this.auditPage--;
          this.loadAuditData();
        }
      });
    }

    if (this.btnAuditNext) {
      this.btnAuditNext.addEventListener("click", () => {
        const logs = this.auditData?.recent_logs || [];
        if (logs.length === this.auditLimit) {
          this.auditOffset += this.auditLimit;
          this.auditPage++;
          this.loadAuditData();
        }
      });
    }
  }

  updateSortHeaders() {
    document.querySelectorAll(".sort-header").forEach(th => {
      const arrow = th.querySelector(".sort-arrow");
      if (!arrow) return;
      if (th.dataset.sort === this.sortField) {
        arrow.textContent = this.sortDirection === "asc" ? "▲" : "▼";
        th.style.color = "var(--primary)";
      } else {
        arrow.textContent = "↕";
        th.style.color = "";
      }
    });
  }

  switchTab(tabName) {
    document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
    document.querySelectorAll(".tab-pane").forEach(p => p.classList.remove("active"));

    const activeBtn = document.querySelector(`.tab-btn[data-tab="${tabName}"]`);
    const activePane = document.getElementById(`pane-${tabName}`);
    if (activeBtn) activeBtn.classList.add("active");
    if (activePane) activePane.classList.add("active");

    if (tabName === "audit") {
      this.loadAuditData();
    }
  }

  loadAuditData() {
    this.sendAction("get_commands_audit", {
      hours: this.auditHours,
      limit: this.auditLimit,
      offset: this.auditOffset
    });
  }

  // ==========================================================================
  // Conexión WebSocket & Reconexión
  // ==========================================================================
  connectWebSocket() {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = window.location.host || "127.0.0.1:8680";
    const wsUrl = `${protocol}//${host}`;

    this.setWsStatus(false, "Conectando...");

    try {
      this.ws = new WebSocket(wsUrl);

      this.ws.onopen = () => {
        console.log("[Mesh WS] Conectado exitosamente");
        this.setWsStatus(true, "Conectado");
        this.showToast("Conectado a la pasarela WebSocket");
        // Solicitar snapshot completo inicial
        this.requestFullSnapshot();
        // Sincronización suave cada 20s para estadísticas globales
        if (this.syncInterval) clearInterval(this.syncInterval);
        this.syncInterval = setInterval(() => this.requestFullSnapshot(), 20000);
      };

      this.ws.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          this.handleIncomingMessage(payload);
        } catch (err) {
          console.error("[WS Parse Error]", err, event.data);
        }
      };

      this.ws.onclose = () => {
        this.setWsStatus(false, "Reconectando en 3s...");
        this.scheduleReconnect();
      };

      this.ws.onerror = () => {
        this.setWsStatus(false, "Error");
        this.ws.close();
      };
    } catch (e) {
      this.setWsStatus(false, "Fallo conexión");
      this.scheduleReconnect();
    }
  }

  scheduleReconnect() {
    if (!this.reconnectTimer) {
      this.reconnectTimer = setTimeout(() => this.connectWebSocket(), 3000);
    }
  }

  setWsStatus(online, text) {
    if (this.ledWs) this.ledWs.className = `led ${online ? "online" : "offline"}`;
    if (this.lblWs) this.lblWs.textContent = text;
  }

  setUartStatus(online, port) {
    if (this.ledUart) this.ledUart.className = `led ${online ? "online" : "offline"}`;
    if (this.lblUart) this.lblUart.textContent = online ? `Activo (${port || "UART"})` : "Desconectado";
  }

  // ==========================================================================
  // Despacho de Mensajes y Eventos
  // ==========================================================================
  handleIncomingMessage(payload) {
    // 1. Mensaje de bienvenida
    if (payload.event === "welcome") {
      if (payload.data?.system_status) {
        this.setUartStatus(payload.data.system_status.uart_connected, payload.data.system_status.serial_port);
      }
      if (payload.data?.local_node) {
        this.localNode = payload.data.local_node;
        const name = this.localNode.short_name || this.localNode.my_node_id || "Bot";
        if (this.lblLocalNode) this.lblLocalNode.textContent = name;
      }
      this.requestFullSnapshot();
      return;
    }

    // 2. Respuesta a una acción previa
    if (payload.type === "response") {
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
      case "message_rx":
        this.addMessage(data, ts);
        break;
      case "node_updated":
        if (data.id && String(data.id).trim() && data.id !== "None" && data.id !== "Desconocido") {
          const prev = this.nodesMap.get(data.id) || {};
          this.nodesMap.set(data.id, { ...prev, ...data });
          this.renderNodesTable();
        }
        break;
      case "device_telemetry":
        if (data.id && this.nodesMap.has(data.id)) {
          const node = this.nodesMap.get(data.id);
          if (data.battery !== undefined) node.battery = data.battery;
          if (data.voltage !== undefined) node.voltage = data.voltage;
          this.renderNodesTable();
        }
        break;
      case "system_status":
        this.setUartStatus(data.uart_connected, data.serial_port);
        break;
      case "channel_metrics":
        if (this.lblChUtil && data.channel_util !== undefined && data.channel_util !== null) {
          this.lblChUtil.textContent = `${Number(data.channel_util).toFixed(1)}%`;
        }
        if (this.lblAirTx && data.air_util_tx !== undefined && data.air_util_tx !== null) {
          this.lblAirTx.textContent = `${Number(data.air_util_tx).toFixed(1)}%`;
        }
        break;
      case "local_node_info":
        if (data) {
          this.localNode = data;
          if (this.lblLocalNode) this.lblLocalNode.textContent = data.short_name || data.name || data.my_node_id || "Bot";
        }
        break;
      case "trace_completed":
        this.renderTraceResult(data, ts);
        this.showToast(`Traceroute finalizado a ${data.to_name || data.to}`);
        break;
      case "router_status":
        if (data.routers) this.renderRouters(data.routers);
        break;
      case "poll_created":
        this.sendAction("get_polls");
        break;
      case "message_ack":
        this.showToast(`Mensaje entregado con éxito a ${data.dest}`);
        break;
    }
  }

  requestFullSnapshot() {
    this.sendAction("get_snapshot", {
      include: ["nodes", "routers", "recent_messages", "stats", "system_status", "local_node", "channel_metrics", "traces"]
    });
    this.sendAction("get_polls");
    this.sendAction("get_weather");
  }

  handleActionResponse(resp) {
    if (!resp.success) {
      this.showToast(`Error: ${resp.error || "Acción fallida"}`, "danger");
      return;
    }

    const data = resp.data;
    if (!data) return;

    if (resp.action === "get_snapshot") {
      // 1. Mensajes: Reconciliación no destructiva
      if (data.recent_messages && Array.isArray(data.recent_messages)) {
        if (this.messages.length === 0) {
          data.recent_messages.forEach(m => {
            if (m.data) this.messages.push({ ...m.data, ts: m.ts });
            else this.messages.push(m);
          });
          this.renderMessages();
        } else {
          let added = false;
          data.recent_messages.forEach(m => {
            const item = m.data ? { ...m.data, ts: m.ts } : m;
            const exists = this.messages.some(old => 
              (old.id && item.id && old.id === item.id) ||
              (old.ts === item.ts && old.text === item.text && old.from === item.from) ||
              (old.is_optimistic && old.text === item.text && String(old.channel ?? 0) === String(item.channel ?? 0))
            );
            if (!exists) {
              this.messages.push(item);
              added = true;
            }
          });
          if (added) {
            this.messages.sort((a, b) => (a.ts || "").localeCompare(b.ts || ""));
            this.renderMessages();
          }
        }
      }

      // 2. Canales
      if (data.channels) {
        this.channels = data.channels;
        this.renderChannelFiltersAndDestinations();
      }

      // 3. Routers
      if (data.routers && Array.isArray(data.routers)) this.renderRouters(data.routers);

      // 4. Nodos
      if (data.nodes && Array.isArray(data.nodes)) {
        data.nodes.forEach(n => {
          const id = n.id || n.node_id;
          if (id && String(id).trim() && id !== "None" && id !== "null" && id !== "Desconocido") {
            this.nodesMap.set(id, { ...(this.nodesMap.get(id) || {}), ...n });
          }
        });
        this.renderNodesTable();
        this.renderChannelFiltersAndDestinations();
      }

      // 5. Traces
      if (data.traces && Array.isArray(data.traces)) {
        if (this.tracesGrid) {
          this.tracesGrid.innerHTML = "";
          data.traces.forEach(tr => this.renderTraceResult(tr, tr.updated_at || tr.created_at));
        }
      }

      // 6. UART, Local Node y Métricas de Canal
      if (data.system_status) this.setUartStatus(data.system_status.uart_connected, data.system_status.serial_port);
      if (data.local_node) {
        this.localNode = data.local_node;
        if (this.lblLocalNode) this.lblLocalNode.textContent = this.localNode.short_name || this.localNode.my_node_id;
      }
      if (data.channel_metrics) {
        if (this.lblChUtil && data.channel_metrics.channel_util !== undefined && data.channel_metrics.channel_util !== null) {
          this.lblChUtil.textContent = `${Number(data.channel_metrics.channel_util).toFixed(1)}%`;
        }
        if (this.lblAirTx && data.channel_metrics.air_util_tx !== undefined && data.channel_metrics.air_util_tx !== null) {
          this.lblAirTx.textContent = `${Number(data.channel_metrics.air_util_tx).toFixed(1)}%`;
        }
      }
    } else if (resp.action === "get_polls") {
      this.renderPolls(data.polls || []);
    } else if (resp.action === "get_weather") {
      this.renderWeather(data);
    } else if (resp.action === "get_commands_audit") {
      this.renderAuditData(data);
    } else if (resp.action === "set_node_favorite") {
      if (data.node_id && this.nodesMap.has(data.node_id)) {
        this.nodesMap.get(data.node_id).is_favorite = data.is_favorite;
        this.renderNodesTable();
      }
    }
  }

  // ==========================================================================
  // Canales y Destinatarios
  // ==========================================================================
  renderChannelFiltersAndDestinations() {
    // 1. Renderizar chips de filtro de chat
    const filterWrap = document.getElementById("chat-filters-wrap");
    if (filterWrap && this.channels) {
      let chipsHtml = `<span style="font-size: 0.8rem; color: var(--text-muted); margin-right: 4px;">Filtrar:</span>`;
      chipsHtml += `<button class="filter-chip ${this.currentChannelFilter === "all" ? "active" : ""}" data-ch="all">Todos</button>`;

      for (const [chNum, chObj] of Object.entries(this.channels)) {
        const name = chObj.name || `Canal ${chNum}`;
        const active = String(this.currentChannelFilter) === String(chNum) ? "active" : "";
        chipsHtml += `<button class="filter-chip ${active}" data-ch="${chNum}">Ch ${chNum} (${name})</button>`;
      }

      chipsHtml += `<button class="filter-chip ${this.currentChannelFilter === "direct" ? "active" : ""}" data-ch="direct">Privados / Directos</button>`;
      filterWrap.innerHTML = chipsHtml;

      // Re-enlazar eventos
      filterWrap.querySelectorAll(".filter-chip").forEach(btn => {
        btn.addEventListener("click", () => {
          filterWrap.querySelectorAll(".filter-chip").forEach(b => b.classList.remove("active"));
          btn.classList.add("active");
          this.currentChannelFilter = btn.dataset.ch;
          this.renderMessages();
        });
      });
    }

    // 2. Renderizar opciones del selector de destino en el formulario
    if (this.chatDest && this.channels) {
      const currentVal = this.chatDest.value;
      let optsHtml = "";

      optsHtml += `<optgroup label="Canales Públicos">`;
      for (const [chNum, chObj] of Object.entries(this.channels)) {
        const name = chObj.name || `Canal ${chNum}`;
        optsHtml += `<option value="^all:${chNum}">Canal ${chNum} (${name})</option>`;
      }
      optsHtml += `</optgroup>`;

      // Añadir favoritos
      const favs = Array.from(this.nodesMap.values()).filter(n => n.is_favorite);
      if (favs.length > 0) {
        optsHtml += `<optgroup label="Nodos Favoritos">`;
        favs.forEach(f => {
          const label = f.short_name ? `${f.short_name} (${f.id})` : (f.name || f.id);
          optsHtml += `<option value="${f.id}">⭐ ${this.escapeHtml(label)}</option>`;
        });
        optsHtml += `</optgroup>`;
      }

      this.chatDest.innerHTML = optsHtml;
      if (currentVal) this.chatDest.value = currentVal;
    }
  }

  // ==========================================================================
  // Renderizado: Live Chat (Sin Parpadeos y Sin Duplicados)
  // ==========================================================================
  addMessage(msg, ts) {
    const timestamp = ts || new Date().toISOString();
    
    // Si viene un mensaje saliente/confirmado del bot, reconciliar optimista
    const isBotSender = (msg.from === this.localNode?.my_node_id || msg.from_name === "Bot (Local)" || msg.is_outgoing);
    
    if (isBotSender) {
      const pendingIdx = this.messages.findIndex(old => 
        old.is_optimistic && 
        old.text === msg.text && 
        String(old.channel ?? 0) === String(msg.channel ?? 0)
      );
      if (pendingIdx !== -1) {
        this.messages[pendingIdx] = {
          ...this.messages[pendingIdx],
          ...msg,
          ts: timestamp,
          is_optimistic: false,
          is_outgoing: true,
          from_name: "Bot (Local)",
        };
        this.renderMessages();
        return;
      }
    }

    const exists = this.messages.some(old => 
      (old.local_id && msg.local_id && old.local_id === msg.local_id) ||
      (old.text === msg.text && old.from === msg.from && Math.abs(new Date(old.ts || 0) - new Date(timestamp)) < 2500)
    );

    if (!exists) {
      this.messages.push({ ...msg, ts: timestamp });
      if (this.messages.length > 150) this.messages.shift();
      this.renderMessages();
    }
  }

  renderMessages() {
    if (!this.chatFeed) return;

    const filtered = this.messages.filter(m => {
      if (this.currentChannelFilter === "all") return true;
      if (this.currentChannelFilter === "direct") return !!m.is_direct;
      return String(m.channel ?? 0) === String(this.currentChannelFilter) && !m.is_direct;
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
      // Si no tiene nombre largo ni corto, mostrar siempre su ID hexadecimal
      let senderName = m.from_name || m.from_short_name || m.from || m.node_id || "Desconocido";
      if (senderName === "Desconocido" && m.from) senderName = m.from;

      const timeStr = m.ts ? m.ts.replace("T", " ").substring(11, 19) : "--:--";
      const isDirect = m.is_direct;
      const chNum = m.channel ?? 0;
      const chName = (this.channels && this.channels[chNum]?.name) ? `Ch ${chNum} (${this.channels[chNum].name})` : `Canal ${chNum}`;
      
      const channelBadge = isDirect 
        ? `<span class="badge badge-direct">Directo</span>`
        : `<span class="badge badge-ch0">${this.escapeHtml(chName)}</span>`;
      const mqttBadge = m.via_mqtt ? `<span class="badge badge-mqtt">MQTT</span>` : "";
      const outBadge = m.is_outgoing ? `<span class="badge" style="background: var(--success-bg); color: var(--success);">Enviado</span>` : "";
      
      // Claridad de SNR: Directo vs Último Salto
      let snrText = "";
      if (m.snr !== undefined && m.snr !== null) {
        const isDirSignal = (m.hops === 0 || isDirect);
        const snrLabel = isDirSignal ? "SNR Directo" : `SNR Último Salto`;
        snrText = `${snrLabel}: ${Number(m.snr).toFixed(1)}dB`;
      }
      const hopsText = (m.hops !== undefined && m.hops !== null && m.hops > 0) ? `${m.hops} ${m.hops === 1 ? "salto" : "saltos"}` : "";

      return `
        <div class="msg-card" style="${m.is_outgoing ? "border-left: 3px solid var(--primary);" : ""}">
          <div class="msg-header">
            <div style="display: flex; align-items: center; gap: 8px;">
              ${channelBadge}
              ${mqttBadge}
              ${outBadge}
              <span class="msg-sender">${this.escapeHtml(senderName)}</span>
              <span style="font-size: 0.75rem; color: var(--text-dim); font-family: monospace;">${this.escapeHtml(m.from || "")}</span>
            </div>
            <span class="msg-meta">${timeStr}</span>
          </div>
          <div class="msg-body">${this.escapeHtml(m.text || "")}</div>
          <div class="msg-footer">
            ${snrText ? `<span>${snrText}</span>` : ""}
            ${hopsText ? `<span>• ${hopsText}</span>` : ""}
          </div>
        </div>
      `;
    }).join("");

    this.chatFeed.scrollTop = this.chatFeed.scrollHeight;
  }

  handleSendMessage() {
    const text = this.chatText.value.trim();
    if (!text) return;

    const destValue = this.chatDest.value;
    let dest = "^all";
    let channel = 0;

    if (destValue.startsWith("^all:")) {
      channel = parseInt(destValue.split(":")[1], 10) || 0;
      dest = "^all";
    } else {
      dest = destValue;
    }

    const localId = "out_" + Date.now();

    this.sendAction("send_message", {
      text: text,
      dest: dest,
      channel: channel,
    });

    // Añadir optimista al feed local
    this.addMessage({
      local_id: localId,
      is_optimistic: true,
      from: this.localNode?.my_node_id || "local",
      from_name: this.localNode?.short_name || "Bot (Local)",
      from_short_name: "BOT",
      to: dest,
      channel: channel,
      text: text,
      is_direct: (dest !== "^all"),
      is_outgoing: true,
    });

    this.chatText.value = "";
    this.showToast("Mensaje encolado para transmisión");
  }

  // ==========================================================================
  // Renderizado: Routers (Ordenación: Online/Directos/SNR y Ruta Completa)
  // ==========================================================================
  renderRouters(routers) {
    if (!this.routersGrid) return;
    if (this.countRouters) this.countRouters.textContent = routers.length;

    if (routers.length === 0) {
      this.routersGrid.innerHTML = `<div style="color: var(--text-dim);">No hay routers configurados en env.ROUTER_NODES.</div>`;
      return;
    }

    // Ordenación estratégica:
    // 1. ONLINE primero, OFFLINE al final
    // 2. En ONLINE: Directos primero (menor saltos), luego mayor SNR
    const sortedRouters = [...routers].sort((a, b) => {
      const isOnlineA = (a.status === "online") || (a.last_seen_sec !== undefined && a.last_seen_sec !== null && a.last_seen_sec < 86400);
      const isOnlineB = (b.status === "online") || (b.last_seen_sec !== undefined && b.last_seen_sec !== null && b.last_seen_sec < 86400);

      if (isOnlineA !== isOnlineB) return isOnlineB ? 1 : -1;

      // Ambos online:
      const hopsA = a.trace_hops !== undefined ? a.trace_hops : (a.hops !== undefined ? a.hops : 99);
      const hopsB = b.trace_hops !== undefined ? b.trace_hops : (b.hops !== undefined ? b.hops : 99);

      if (hopsA !== hopsB) return hopsA - hopsB;

      // A igual saltos, mayor SNR primero
      const snrA = a.snr !== undefined && a.snr !== null ? Number(a.snr) : -99;
      const snrB = b.snr !== undefined && b.snr !== null ? Number(b.snr) : -99;
      return snrB - snrA;
    });

    this.routersGrid.innerHTML = sortedRouters.map(r => {
      const isOnline = (r.status === "online") || (r.last_seen_sec !== undefined && r.last_seen_sec !== null && r.last_seen_sec < 86400);
      
      // Construir indicador de Enlace y Ruta
      let routeBadge = "";
      let signalDetails = "";
      
      if (r.trace_hops !== undefined && r.trace_hops !== null) {
        if (r.trace_hops === 0) {
          routeBadge = `<span class="badge" style="background: var(--success-bg); color: var(--success);">Directo a Base (RAU0)</span>`;
          signalDetails = `<strong>${this.escapeHtml(r.trace_snr_text || "")}</strong>`;
        } else {
          routeBadge = `<span class="badge" style="background: var(--primary-bg); color: var(--primary);">${r.trace_hops} ${r.trace_hops === 1 ? "salto" : "saltos"}</span>`;
          const inters = (r.trace_intermediates && r.trace_intermediates.length > 0) ? r.trace_intermediates.join(" ➔ ") : "";
          const routeStr = inters ? `RAU0 ➔ ${inters} ➔ ${r.name || r.id}` : `RAU0 ➔ ${r.name || r.id}`;
          signalDetails = `<div><strong>${this.escapeHtml(r.trace_snr_text || "")}</strong></div><div style="font-size: 0.75rem; color: var(--text-dim); margin-top: 2px;">Ruta: ${this.escapeHtml(routeStr)}</div>`;
        }
      } else if (r.snr !== undefined && r.snr !== null) {
        const isDir = (r.hops === 0);
        routeBadge = `<span class="badge badge-ch0">${isDir ? "Directo (RF)" : r.hops + " saltos (RF)"}</span>`;
        signalDetails = `<strong>${Number(r.snr).toFixed(1)} dB</strong>`;
      } else {
        signalDetails = "--";
      }

      // Batería si está disponible
      let batteryStr = "";
      if (r.battery !== undefined && r.battery !== null) {
        const bVal = r.battery > 100 ? "⚡ 100%" : `${r.battery}%`;
        const vVal = (r.voltage !== undefined && r.voltage !== null) ? ` (${Number(r.voltage).toFixed(2)}V)` : "";
        batteryStr = `<div class="card-row"><span>Batería:</span><span style="color: var(--success); font-weight: 600;">${bVal}${vVal}</span></div>`;
      } else if (r.voltage !== undefined && r.voltage !== null) {
        batteryStr = `<div class="card-row"><span>Voltaje:</span><span>${Number(r.voltage).toFixed(2)}V</span></div>`;
      }

      let lastSeen = "sin señal";
      if (r.last_seen_sec !== undefined && r.last_seen_sec !== null) {
        const s = r.last_seen_sec;
        if (s < 60) lastSeen = `hace ${s}s`;
        else if (s < 3600) lastSeen = `hace ${Math.floor(s / 60)}m`;
        else if (s < 86400) lastSeen = `hace ${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`;
        else lastSeen = `hace ${Math.floor(s / 86400)}d`;
      }

      const routerId = r.id || r.node_id || r.name;

      return `
        <div class="card">
          <div class="card-header">
            <span>${this.escapeHtml(r.name || routerId)}</span>
            <div style="display: flex; gap: 4px; align-items: center;">
              ${routeBadge}
              <span class="badge" style="background: ${isOnline ? "var(--success-bg)" : "var(--danger-bg)"}; color: ${isOnline ? "var(--success)" : "var(--danger)"};">
                ${isOnline ? "ONLINE" : "OFFLINE"}
              </span>
            </div>
          </div>
          <div class="card-row">
            <span>ID Hex:</span>
            <span style="font-family: monospace;">${this.escapeHtml(routerId)}</span>
          </div>
          <div class="card-row">
            <span>Calidad / Ruta:</span>
            <span>${signalDetails}</span>
          </div>
          ${batteryStr}
          <div class="card-row">
            <span>Última señal:</span>
            <span>${lastSeen}</span>
          </div>
          <button class="btn-secondary" style="margin-top: 6px; width: 100%; font-weight: 600;" onclick="window.dashboard.requestTraceTo('${routerId}', this)">
            📍 Lanzar Traceroute
          </button>
        </div>
      `;
    }).join("");
  }

  requestTraceTo(nodeId, btn) {
    if (btn) {
      btn.disabled = true;
      btn.textContent = "Encolando...";
      setTimeout(() => { btn.disabled = false; btn.textContent = "📍 Lanzar Traceroute"; }, 3000);
    }
    this.sendAction("request_trace", { dest: nodeId });
    this.showToast(`Traceroute encolado hacia ${nodeId}`);
  }

  requestNodeInfo(nodeId, btn) {
    if (btn) {
      btn.disabled = true;
      btn.textContent = "Pidiendo...";
      setTimeout(() => { btn.disabled = false; btn.textContent = "ℹ️ Info"; }, 3000);
    }
    this.sendAction("request_node_info", { node_id: nodeId });
    this.showToast(`Petición NodeInfo enviada a ${nodeId}`);
  }

  // ==========================================================================
  // Renderizado: Nodos (Filtro por Rol, Primera Vez y Solicitud de NodeInfo)
  // ==========================================================================
  renderNodesTable() {
    if (!this.nodesTbody) return;

    let nodes = Array.from(this.nodesMap.values()).filter(n => {
      const id = n.id || n.node_id;
      return id && String(id).trim() && id !== "None" && id !== "null" && id !== "Desconocido";
    });
    if (this.countNodes) this.countNodes.textContent = nodes.length;

    // 1. Filtro texto (busca por nombre largo, nombre corto o ID)
    if (this.searchQuery) {
      nodes = nodes.filter(n => {
        const id = (n.id || "").toLowerCase();
        const name = (n.name || "").toLowerCase();
        const short = (n.short_name || "").toLowerCase();
        return id.includes(this.searchQuery) || name.includes(this.searchQuery) || short.includes(this.searchQuery);
      });
    }

    // 2. Filtro por Rol
    if (this.currentRoleFilter && this.currentRoleFilter !== "all") {
      nodes = nodes.filter(n => (n.role_name || "").toUpperCase() === this.currentRoleFilter.toUpperCase());
    }

    // 3. Filtro categoría
    if (this.currentNodeFilter === "rf") {
      nodes = nodes.filter(n => !n.via_mqtt);
    } else if (this.currentNodeFilter === "fav") {
      nodes = nodes.filter(n => n.is_favorite);
    }

    // 4. Ordenación Multidimensional
    const field = this.sortField;
    const dir = this.sortDirection === "asc" ? 1 : -1;

    nodes.sort((a, b) => {
      let valA = a[field];
      let valB = b[field];

      if (field === "is_favorite") {
        valA = valA ? 1 : 0;
        valB = valB ? 1 : 0;
      } else if (field === "battery" || field === "snr" || field === "hops" || field === "uptime") {
        valA = (valA !== undefined && valA !== null) ? Number(valA) : -999999;
        valB = (valB !== undefined && valB !== null) ? Number(valB) : -999999;
      } else if (field === "last_heard" || field === "created_at") {
        const tA = this.parseDateTimestamp(valA || a.updated_at);
        const tB = this.parseDateTimestamp(valB || b.updated_at);
        valA = tA;
        valB = tB;
      } else {
        valA = (valA || "").toString().toLowerCase();
        valB = (valB || "").toString().toLowerCase();
      }

      if (valA < valB) return -1 * dir;
      if (valA > valB) return 1 * dir;
      return 0;
    });

    if (nodes.length === 0) {
      this.nodesTbody.innerHTML = `
        <tr>
          <td colspan="11" style="text-align: center; color: var(--text-dim); padding: 20px;">
            No se encontraron nodos con los filtros aplicados.
          </td>
        </tr>`;
      return;
    }

    this.nodesTbody.innerHTML = nodes.map(n => {
      const isFav = !!n.is_favorite;
      
      // Formateo de Batería y Voltaje
      let battery = "--";
      if (n.battery !== undefined && n.battery !== null) {
        if (n.battery > 100) battery = "⚡ 100%";
        else battery = `${n.battery}%`;
        if (n.voltage !== undefined && n.voltage !== null) {
          battery += ` <span style="color: var(--text-dim); font-size: 0.75rem;">(${Number(n.voltage).toFixed(2)}V)</span>`;
        }
      } else if (n.voltage !== undefined && n.voltage !== null) {
        battery = `${Number(n.voltage).toFixed(2)}V`;
      }

      const snr = n.snr !== undefined && n.snr !== null ? `${Number(n.snr).toFixed(1)} dB` : "--";
      const hops = n.hops !== undefined && n.hops !== null ? n.hops : "--";
      const nodeId = n.id || n.node_id;

      // Última señal inteligente (last_heard o updated_at)
      const lastHeardStr = this.formatRelativeOrDate(n.last_heard || n.updated_at);

      // Primera vez visto (created_at)
      const createdAtStr = this.formatDateOnly(n.created_at || n.updated_at);

      return `
        <tr>
          <td>
            <button class="star-btn ${isFav ? "fav" : ""}" onclick="window.dashboard.toggleFavorite('${nodeId}', ${!isFav})">
              ★
            </button>
          </td>
          <td>
            <strong>${this.escapeHtml(n.name || "Sin nombre")}</strong>
          </td>
          <td style="font-weight: 600; color: var(--primary); font-family: monospace;">
            ${this.escapeHtml(n.short_name || "--")}
          </td>
          <td style="font-family: monospace; font-size: 0.85rem;">${this.escapeHtml(nodeId || "")}</td>
          <td><span class="badge" style="background: var(--primary-bg); color: var(--primary);">${this.escapeHtml(n.role_name || "CLIENT")}</span></td>
          <td>${hops}</td>
          <td>${battery}</td>
          <td>${snr}</td>
          <td style="font-size: 0.8rem; color: var(--text-muted);">${lastHeardStr}</td>
          <td style="font-size: 0.8rem; color: var(--text-dim);">${createdAtStr}</td>
          <td>
            <div style="display: flex; gap: 4px;">
              <button class="btn-secondary" style="padding: 3px 6px; font-size: 0.75rem;" title="Lanzar Traceroute" onclick="window.dashboard.requestTraceTo('${nodeId}', this)">
                Trace
              </button>
              <button class="btn-secondary" style="padding: 3px 6px; font-size: 0.75rem;" title="Pedir NodeInfo por LoRa" onclick="window.dashboard.requestNodeInfo('${nodeId}', this)">
                ℹ️ Info
              </button>
            </div>
          </td>
        </tr>
      `;
    }).join("");
  }

  toggleFavorite(nodeId, makeFav) {
    this.sendAction("set_node_favorite", { node_id: nodeId, is_favorite: makeFav });
  }

  parseDateTimestamp(val) {
    if (!val) return 0;
    if (typeof val === "number") return val > 10000000000 ? val : val * 1000;
    if (typeof val === "string") {
      if (/^\d+$/.test(val)) {
        const num = parseInt(val, 10);
        return num > 10000000000 ? num : num * 1000;
      }
      const parsed = Date.parse(val);
      return isNaN(parsed) ? 0 : parsed;
    }
    return 0;
  }

  formatRelativeOrDate(val) {
    const ms = this.parseDateTimestamp(val);
    if (!ms) return "--";
    const d = new Date(ms);
    const now = new Date();
    const isToday = d.toDateString() === now.toDateString();
    
    if (isToday) {
      return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    } else {
      const day = String(d.getDate()).padStart(2, "0");
      const month = String(d.getMonth() + 1).padStart(2, "0");
      const time = d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
      return `${day}/${month} ${time}`;
    }
  }

  formatDateOnly(val) {
    const ms = this.parseDateTimestamp(val);
    if (!ms) return "--";
    const d = new Date(ms);
    const day = String(d.getDate()).padStart(2, "0");
    const month = String(d.getMonth() + 1).padStart(2, "0");
    const year = d.getFullYear();
    return `${day}/${month}/${year}`;
  }

  // ==========================================================================
  // Renderizado: Traceroutes (Manejo correcto de Fallidos)
  // ==========================================================================
  renderTraceResult(trace, ts) {
    if (!this.tracesGrid) return;

    const timeStr = ts ? ts.replace("T", " ").substring(0, 19) : new Date().toLocaleString();
    const hopsFwd = trace.hops_forward || [];
    
    let fwdStr = "";
    if (trace.success) {
      if (hopsFwd.length > 0) {
        fwdStr = hopsFwd.map(h => `${this.escapeHtml(h.name || h.id)} (${h.snr !== undefined && h.snr !== null ? h.snr + "dB" : ""})`).join(" ➔ ");
      } else {
        const directSnr = trace.snr !== undefined && trace.snr !== null ? ` (SNR: ${Number(trace.snr).toFixed(1)} dB)` : "";
        fwdStr = `Directo / Sin repetidores intermedios${directSnr}`;
      }
    } else {
      fwdStr = `<span style="color: var(--danger);">⚠️ Sin respuesta del nodo destino (Timeout / Sin cobertura)</span>`;
    }

    const cardHtml = `
      <div class="card" style="border-left: 4px solid var(--primary);">
        <div class="card-header">
          <span>Destino: ${this.escapeHtml(trace.to_name || trace.to)}</span>
          <span class="badge" style="background: ${trace.success ? "var(--success-bg)" : "var(--danger-bg)"}; color: ${trace.success ? "var(--success)" : "var(--danger)"};">
            ${trace.success ? "ÉXITO" : "FALLIDO"}
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
          </div>` : ""}
      </div>
    `;

    if (this.tracesGrid.innerHTML.includes("No hay traceroutes")) {
      this.tracesGrid.innerHTML = cardHtml;
    } else {
      this.tracesGrid.insertAdjacentHTML("afterbegin", cardHtml);
    }
  }

  // ==========================================================================
  // Renderizado: Auditoría y Estadísticas de Comandos
  // ==========================================================================
  renderAuditData(data) {
    this.auditData = data;
    const summary = data.summary || {};
    const ranking = data.ranking || [];

    // 1. Tarjetas de Resumen
    if (this.auditTotalCmds) this.auditTotalCmds.textContent = summary.total ?? "--";
    if (this.auditTotalPeriod) {
      if (this.auditHours === 1) this.auditTotalPeriod.textContent = "en la última hora";
      else if (this.auditHours) this.auditTotalPeriod.textContent = `en las últimas ${this.auditHours}h`;
      else this.auditTotalPeriod.textContent = "histórico total";
    }
    if (this.auditUniqueNodes) this.auditUniqueNodes.textContent = summary.unique_nodes ?? "--";
    if (this.auditTopCommand) this.auditTopCommand.textContent = summary.top_command ? `/${summary.top_command}` : "N/D";
    if (this.auditTopCommandCount) this.auditTopCommandCount.textContent = summary.top_command_count ? `${summary.top_command_count} peticiones` : "--";
    if (this.auditTopUser) this.auditTopUser.textContent = summary.top_user || "N/D";
    if (this.auditTopUserCount) this.auditTopUserCount.textContent = summary.top_user_count ? `${summary.top_user_count} comandos` : "--";

    // 2. Ranking de Nodos (Top 20)
    if (this.auditRankingTbody) {
      if (ranking.length === 0) {
        this.auditRankingTbody.innerHTML = `
          <tr><td colspan="6" style="text-align: center; color: var(--text-dim); padding: 20px;">No hay comandos registrados en este periodo.</td></tr>
        `;
      } else {
        this.auditRankingTbody.innerHTML = ranking.map((r, idx) => {
          const isHeavy = r.count > 20;
          const warningBadge = isHeavy ? `<span class="badge" style="background: var(--danger-bg); color: var(--danger); margin-left: 4px;">Uso Alto</span>` : "";
          const name = r.name || r.short_name || r.node_id || "Desconocido";
          
          // Formateo de fecha en ranking: si es >24h o total, mostrar fecha completa
          let lastTime = "--:--";
          if (r.last_command_at) {
            if (this.auditHours === 1 || this.auditHours === 24) {
              lastTime = r.last_command_at.replace("T", " ").substring(11, 19);
            } else {
              lastTime = r.last_command_at.replace("T", " ").substring(0, 16);
            }
          }

          return `
            <tr>
              <td style="font-weight: 700; color: var(--text-dim);">${idx + 1}</td>
              <td>
                <strong>${this.escapeHtml(name)}</strong>
                ${r.short_name ? `<span style="font-size: 0.75rem; color: var(--primary); margin-left: 4px;">[${this.escapeHtml(r.short_name)}]</span>` : ""}
                ${warningBadge}
              </td>
              <td style="font-family: monospace; font-size: 0.85rem;">${this.escapeHtml(r.node_id || "")}</td>
              <td><span class="badge" style="background: var(--primary-bg); color: var(--primary); font-weight: 700;">${r.count}</span></td>
              <td><code style="color: var(--warning);">/${this.escapeHtml(r.last_command || "")}</code></td>
              <td style="font-size: 0.8rem; color: var(--text-muted);">${lastTime}</td>
            </tr>
          `;
        }).join("");
      }
    }

    // 3. Registro Cronológico y Paginación
    if (this.lblAuditPage) {
      this.lblAuditPage.textContent = `Página ${this.auditPage}`;
    }
    this.renderAuditLogs();
  }

  renderAuditLogs() {
    if (!this.auditLogsTbody || !this.auditData) return;
    let logs = this.auditData.recent_logs || [];

    if (this.auditSearchQuery) {
      logs = logs.filter(l => {
        const cmd = (l.command || "").toLowerCase();
        const nid = (l.node_id || "").toLowerCase();
        const name = (l.name || "").toLowerCase();
        const sname = (l.short_name || "").toLowerCase();
        return cmd.includes(this.auditSearchQuery) || nid.includes(this.auditSearchQuery) || name.includes(this.auditSearchQuery) || sname.includes(this.auditSearchQuery);
      });
    }

    if (logs.length === 0) {
      this.auditLogsTbody.innerHTML = `
        <tr><td colspan="4" style="text-align: center; color: var(--text-dim); padding: 20px;">No hay registros coincidentes.</td></tr>
      `;
      return;
    }

    this.auditLogsTbody.innerHTML = logs.map(l => {
      const timeStr = l.created_at ? l.created_at.replace("T", " ").substring(0, 19) : "--";
      const sender = l.short_name || l.name || l.node_id || "N/D";

      return `
        <tr>
          <td style="font-size: 0.8rem; color: var(--text-muted);">${timeStr}</td>
          <td>
            <strong>${this.escapeHtml(sender)}</strong>
            <div style="font-size: 0.75rem; color: var(--text-dim); font-family: monospace;">${this.escapeHtml(l.node_id || "")}</div>
          </td>
          <td><span class="badge" style="background: var(--primary-bg); color: var(--primary);">/${this.escapeHtml(l.command || "")}</span></td>
          <td style="font-size: 0.85rem; color: var(--text-muted);">${this.escapeHtml(l.message || l.parameters || "--")}</td>
        </tr>
      `;
    }).join("");
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
      const total = p.total_votes || 0;

      const optsHtml = options.map((opt, idx) => {
        const c = counts[idx] || 0;
        const pct = total > 0 ? Math.round((c / total) * 100) : 0;

        return `
          <div style="margin-bottom: 8px;">
            <div style="display: flex; justify-content: space-between; font-size: 0.85rem; margin-bottom: 3px;">
              <span>${this.escapeHtml(opt)}</span>
              <span><strong>${c}</strong> (${pct}%)</span>
            </div>
            <div style="background: var(--bg-main); height: 8px; border-radius: 4px; overflow: hidden;">
              <div style="background: var(--primary); height: 100%; width: ${pct}%;"></div>
            </div>
          </div>
        `;
      }).join("");

      return `
        <div class="card">
          <div class="card-header">
            <span>Encuesta #${p.id}</span>
            <span class="badge" style="background: var(--primary-bg); color: var(--primary);">${total} votos</span>
          </div>
          <div style="font-weight: 600; margin-bottom: 12px; font-size: 1rem;">
            ${this.escapeHtml(p.question)}
          </div>
          ${optsHtml}
          <div style="font-size: 0.75rem; color: var(--text-dim); margin-top: 10px;">
            Creada por ${this.escapeHtml(p.owner_node_id || "N/D")}
          </div>
        </div>
      `;
    }).join("");
  }

  renderWeather(weather) {
    if (!this.weatherContent) return;
    if (!weather || Object.keys(weather).length === 0) {
      this.weatherContent.textContent = "No hay datos meteorológicos recientes en la base de datos.";
      return;
    }

    if (this.weatherProvince && weather.province) {
      this.weatherProvince.textContent = `AEMET · ${weather.province}`;
    }

    this.weatherContent.textContent = weather.summary || weather.data_raw || "Predicción disponible.";
  }

  // ==========================================================================
  // Utilidades y Toasts
  // ==========================================================================
  sendAction(action, params = {}) {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      return;
    }

    const req = {
      action: action,
      req_id: "req_" + Math.random().toString(36).substring(2, 9),
      params: params,
    };

    this.ws.send(JSON.stringify(req));
  }

  showToast(message, type = "info") {
    if (!this.toastContainer) return;

    const toast = document.createElement("div");
    toast.className = "toast";
    if (type === "danger") toast.style.borderLeftColor = "var(--danger)";
    if (type === "warning") toast.style.borderLeftColor = "var(--warning)";
    toast.textContent = message;

    this.toastContainer.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = "0";
      toast.style.transform = "translateY(10px)";
      toast.style.transition = "all 0.3s ease";
      setTimeout(() => toast.remove(), 300);
    }, 3000);
  }

  escapeHtml(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }
}

// Inicialización global al cargar DOM
document.addEventListener("DOMContentLoaded", () => {
  window.dashboard = new MeshDashboard();
});
