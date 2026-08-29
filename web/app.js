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
    this.currentTimeFilter = "all";
    this.sortField = "is_favorite";
    this.sortDirection = "desc";
    this.searchQuery = "";
    this.nodesPage = 1;
    this.nodesPageSize = 100;
    this.localNode = null;
    this.auditHours = 24;
    this.auditLimit = 100;
    this.auditOffset = 0;
    this.auditPage = 1;
    this.auditData = null;
    this.auditSearchQuery = "";
    this.scheduledMessages = [];
    this.blockedNodes = [];
    this.abuseLogs = [];

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
    this.countScheds = document.getElementById("count-scheds");
    this.countBlocked = document.getElementById("count-blocked");

    // Footer Telemetría Hardware (Módulo 05)
    this.ftCpuTemp = document.getElementById("ft-cpu-temp");
    this.ftLoad = document.getElementById("ft-load");
    this.ftRam = document.getElementById("ft-ram");
    this.ftDisk = document.getElementById("ft-disk");
    this.ftUptime = document.getElementById("ft-uptime");
    this.ftUart = document.getElementById("ft-uart");

    // Contenedores
    this.chatFeed = document.getElementById("chat-feed");
    this.chatForm = document.getElementById("chat-form");
    this.chatText = document.getElementById("chat-text");
    this.chatDest = document.getElementById("chat-dest");
    this.routersGrid = document.getElementById("routers-grid");
    this.nodesTbody = document.getElementById("nodes-tbody");
    this.lblNodesCountInfo = document.getElementById("lbl-nodes-count-info");
    this.lblNodesPage = document.getElementById("lbl-nodes-page");
    this.btnNodesPrev = document.getElementById("btn-nodes-prev");
    this.btnNodesNext = document.getElementById("btn-nodes-next");
    this.nodesPageSizeSelect = document.getElementById("nodes-page-size");
    this.tracesGrid = document.getElementById("traces-grid");
    this.pollsContainer = document.getElementById("polls-container");
    this.weatherContent = document.getElementById("weather-content");
    this.weatherProvince = document.getElementById("weather-province");
    this.toastContainer = document.getElementById("toast-container");

    // Elementos de Programación (Módulo 04)
    this.btnToggleSchedForm = document.getElementById("btn-toggle-sched-form");
    this.btnCloseSchedForm = document.getElementById("btn-close-sched-form");
    this.btnCancelSched = document.getElementById("btn-cancel-sched");
    this.schedFormCard = document.getElementById("sched-form-card");
    this.schedFormTitle = document.getElementById("sched-form-title");
    this.btnSubmitSched = document.getElementById("btn-submit-sched");
    this.formCreateSched = document.getElementById("form-create-sched");
    this.schedEditId = document.getElementById("sched-edit-id");
    this.schedMsgText = document.getElementById("sched-msg-text");
    this.schedMsgCharcount = document.getElementById("sched-msg-charcount");
    this.schedMsgPartscount = document.getElementById("sched-msg-partscount");
    this.schedChAll = document.getElementById("sched-ch-all");
    this.schedPeriodType = document.getElementById("sched-period-type");
    this.schedPeriodVal = document.getElementById("sched-period-val");
    this.schedStartAt = document.getElementById("sched-start-at");
    this.schedValWrap = document.getElementById("sched-val-wrap");
    this.schedulesTbody = document.getElementById("schedules-tbody");

    // Elementos de Seguridad y Bloqueos (Módulo 06)
    this.formManualBlock = document.getElementById("form-manual-block");
    this.blockNodeId = document.getElementById("block-node-id");
    this.blockReason = document.getElementById("block-reason");
    this.blockDuration = document.getElementById("block-duration");
    this.btnRefreshSecurity = document.getElementById("btn-refresh-security");
    this.blockedNodesTbody = document.getElementById("blocked-nodes-tbody");
    this.abuseLogsTbody = document.getElementById("abuse-logs-tbody");
    this.autoReportedTbody = document.getElementById("auto-reported-tbody");
    this.filterAutoreportReason = document.getElementById("filter-autoreport-reason");
    this.countReportedBadge = document.getElementById("count-reported-badge");

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

    // Elementos de la Guía de Comandos
    this.commandsContainer = document.getElementById("commands-container");
    this.commandsSearchInput = document.getElementById("commands-search-input");
  }

  bindEvents() {
    // Pestañas
    document.querySelectorAll(".tab-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        const tab = btn.dataset.tab;
        this.switchTab(tab);
      });
    });

    // Búsqueda en Guía de Comandos
    if (this.commandsSearchInput) {
      this.commandsSearchInput.addEventListener("input", (e) => {
        this.renderCommandsGuide(e.target.value);
      });
    }
    this.renderCommandsGuide();

    // Envío de Mensaje Chat
    if (this.chatForm) {
      this.chatForm.addEventListener("submit", (e) => {
        e.preventDefault();
        this.handleSendMessage();
      });
    }

    // Toggle Formulario de Programación
    if (this.btnToggleSchedForm && this.schedFormCard) {
      this.btnToggleSchedForm.addEventListener("click", () => {
        const isHidden = this.schedFormCard.style.display === "none";
        if (isHidden) {
          this.resetScheduleForm();
          this.schedFormCard.style.display = "block";
        } else {
          this.schedFormCard.style.display = "none";
        }
      });
    }
    if (this.btnCloseSchedForm && this.schedFormCard) {
      this.btnCloseSchedForm.addEventListener("click", () => {
        this.resetScheduleForm();
        this.schedFormCard.style.display = "none";
      });
    }
    if (this.btnCancelSched && this.schedFormCard) {
      this.btnCancelSched.addEventListener("click", () => {
        this.resetScheduleForm();
        this.schedFormCard.style.display = "none";
      });
    }

    // Contador de caracteres y cálculo de partes LoRa en mensaje programado
    if (this.schedMsgText) {
      this.schedMsgText.addEventListener("input", (e) => {
        const len = e.target.value.length;
        if (this.schedMsgCharcount) this.schedMsgCharcount.textContent = `${len} / 500 caracteres`;
        if (this.schedMsgPartscount) {
          const parts = Math.max(1, Math.ceil(len / 190));
          this.schedMsgPartscount.textContent = `${parts} ${parts === 1 ? "parte LoRa (~200B)" : "partes LoRa"}`;
          this.schedMsgPartscount.style.color = parts > 3 ? "var(--danger)" : "var(--primary)";
        }
      });
    }

    // Checkbox "Todos los canales"
    if (this.schedChAll) {
      this.schedChAll.addEventListener("change", (e) => {
        const checked = e.target.checked;
        document.querySelectorAll(".sched-ch-item").forEach(cb => {
          cb.checked = checked;
        });
      });
      document.querySelectorAll(".sched-ch-item").forEach(cb => {
        cb.addEventListener("change", () => {
          const allItems = Array.from(document.querySelectorAll(".sched-ch-item"));
          const allChecked = allItems.every(i => i.checked);
          if (this.schedChAll) this.schedChAll.checked = allChecked;
        });
      });
    }

    // Periodicidad select
    if (this.schedPeriodType && this.schedValWrap) {
      this.schedPeriodType.addEventListener("change", (e) => {
        const val = e.target.value;
        this.schedValWrap.style.display = val === "once" ? "none" : "block";
      });
    }

    // Envío de Formulario de Programación
    if (this.formCreateSched) {
      this.formCreateSched.addEventListener("submit", (e) => {
        e.preventDefault();
        this.handleCreateSchedule();
      });
    }

    // Chips de inserción rápida de comandos dinámicos
    document.querySelectorAll(".chip-cmd").forEach(chip => {
      chip.addEventListener("click", () => {
        const cmd = chip.getAttribute("data-cmd");
        if (this.schedMsgText && cmd) {
          this.schedMsgText.value = cmd;
          this.schedMsgText.dispatchEvent(new Event("input"));
          this.schedMsgText.focus();
        }
      });
    });

    // Formulario de Bloqueo Manual
    if (this.formManualBlock) {
      this.formManualBlock.addEventListener("submit", (e) => {
        e.preventDefault();
        this.handleManualBlock();
      });
    }

    // Botón refrescar seguridad
    if (this.btnRefreshSecurity) {
      this.btnRefreshSecurity.addEventListener("click", () => {
        this.loadSecurityData();
        this.showToast("Listas de seguridad actualizadas");
      });
    }

    // Filtro por motivo en Nodos Auto-reportados
    if (this.filterAutoreportReason) {
      this.filterAutoreportReason.addEventListener("change", () => {
        this.loadAutoReportedNodes();
      });
    }

    // Búsqueda de Nodos
    const searchInput = document.getElementById("nodes-search");
    if (searchInput) {
      searchInput.addEventListener("input", (e) => {
        this.searchQuery = e.target.value.toLowerCase().trim();
        this.nodesPage = 1;
        this.renderNodesTable();
      });
    }

    // Filtro por Rol en Nodos
    const roleFilter = document.getElementById("nodes-role-filter");
    if (roleFilter) {
      roleFilter.addEventListener("change", (e) => {
        this.currentRoleFilter = e.target.value;
        this.nodesPage = 1;
        this.renderNodesTable();
      });
    }

    // Filtro por Última Señal en Nodos (1 día / 1 semana / 1 mes / inactivos / todos)
    const timeFilter = document.getElementById("nodes-time-filter");
    if (timeFilter) {
      timeFilter.addEventListener("change", (e) => {
        this.currentTimeFilter = e.target.value;
        this.nodesPage = 1;
        if (this.currentTimeFilter.startsWith("off_")) {
          this.sortField = "last_heard";
          this.sortDirection = "asc"; // Los que llevan más tiempo apagados primero
          this.updateSortHeaders();
        } else if (this.currentTimeFilter !== "all") {
          this.sortField = "last_heard";
          this.sortDirection = "desc"; // Los más recientes primero
          this.updateSortHeaders();
        }
        this.renderNodesTable();
      });
    }

    // Filtro de Nodos (Todos / Batería / RF / Favs)
    document.querySelectorAll(".filter-nodes").forEach(btn => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".filter-nodes").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        this.currentNodeFilter = btn.dataset.filter;
        this.nodesPage = 1;
        if (this.currentNodeFilter === "battery") {
          this.sortField = "battery";
          this.sortDirection = "asc"; // Mostrar primero las baterías más bajas
          this.updateSortHeaders();
        }
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
        this.nodesPage = 1;
        this.updateSortHeaders();
        this.renderNodesTable();
      });
    });

    // Paginación de Nodos
    if (this.nodesPageSizeSelect) {
      this.nodesPageSizeSelect.addEventListener("change", (e) => {
        this.nodesPageSize = e.target.value === "all" ? "all" : parseInt(e.target.value, 10);
        this.nodesPage = 1;
        this.renderNodesTable();
      });
    }

    if (this.btnNodesPrev) {
      this.btnNodesPrev.addEventListener("click", () => {
        if (this.nodesPage > 1) {
          this.nodesPage--;
          this.renderNodesTable();
        }
      });
    }

    if (this.btnNodesNext) {
      this.btnNodesNext.addEventListener("click", () => {
        this.nodesPage++;
        this.renderNodesTable();
      });
    }

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
    } else if (tabName === "schedules") {
      this.loadSchedules();
    } else if (tabName === "security") {
      this.loadSecurityData();
    }
  }

  loadAuditData() {
    this.sendAction("get_commands_audit", {
      hours: this.auditHours,
      limit: this.auditLimit,
      offset: this.auditOffset
    });
  }

  loadSchedules() {
    this.sendAction("get_scheduled_messages");
  }

  loadSecurityData() {
    this.loadAutoReportedNodes();
    this.sendAction("get_blocked_nodes");
    this.sendAction("get_abuse_logs");
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
    if (this.ftUart) {
      this.ftUart.textContent = online ? "Conectado" : "Desconectado";
      this.ftUart.style.color = online ? "var(--success)" : "var(--danger)";
    }
  }

  updateTelemetryFooter(telem) {
    if (!telem) return;
    if (this.ftCpuTemp) {
      this.ftCpuTemp.textContent = telem.cpu_temp ? `${Number(telem.cpu_temp).toFixed(1)}°C` : "--°C";
      if (telem.cpu_temp > 70) this.ftCpuTemp.style.color = "var(--danger)";
      else if (telem.cpu_temp > 55) this.ftCpuTemp.style.color = "var(--warning)";
      else this.ftCpuTemp.style.color = "var(--success)";
    }
    if (this.ftLoad) {
      const l1 = telem.load_1m !== undefined ? telem.load_1m : "--";
      const l5 = telem.load_5m !== undefined ? telem.load_5m : "--";
      this.ftLoad.textContent = `${l1} / ${l5}`;
    }
    if (this.ftRam) {
      const used = telem.ram_used_mb !== undefined ? `${telem.ram_used_mb}MB` : "--";
      const pct = telem.ram_percent !== undefined ? `${telem.ram_percent}%` : "--";
      this.ftRam.textContent = `${used} (${pct})`;
    }
    if (this.ftDisk) {
      this.ftDisk.textContent = telem.disk_free_gb !== undefined ? `${Number(telem.disk_free_gb).toFixed(1)} GB libre` : "--";
    }
    if (this.ftUptime) {
      this.ftUptime.textContent = telem.bot_uptime_human || telem.system_uptime_human || "--";
    }
    if (telem.uart_connected !== undefined) {
      this.setUartStatus(telem.uart_connected, telem.serial_port);
    }
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
      case "system_telemetry":
        this.updateTelemetryFooter(data);
        break;
      case "node_blocked":
        this.showToast(`🚨 Bloqueo aplicado a ${data.node_name || data.node_id}: ${data.reason}`, "warning");
        this.loadSecurityData();
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
      case "auto_report_event":
      case "node_ignore_toggled":
        this.loadAutoReportedNodes();
        break;
      case "message_ack":
        this.showToast(`Mensaje entregado con éxito a ${data.dest}`);
        break;
    }
  }

  requestFullSnapshot() {
    this.sendAction("get_snapshot", {
      include: ["nodes", "routers", "recent_messages", "stats", "system_status", "local_node", "channel_metrics", "traces", "system_telemetry"]
    });
    this.sendAction("get_polls");
    this.sendAction("get_weather");
    this.sendAction("get_scheduled_messages");
    this.sendAction("get_blocked_nodes");
    this.sendAction("get_auto_reported_nodes");
  }

  handleActionResponse(resp) {
    if (!resp.success) {
      this.showToast(`Error: ${resp.error || "Acción fallida"}`, "danger");
      return;
    }

    const data = resp.data;
    if (!data) return;

    if (resp.action === "get_snapshot") {
      // Telemetría de sistema hardware
      if (data.system_telemetry) {
        this.updateTelemetryFooter(data.system_telemetry);
      }

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
    } else if (resp.action === "get_scheduled_messages") {
      this.renderScheduledMessages(data.messages || []);
    } else if (resp.action === "create_scheduled_message") {
      this.showToast("Mensaje programado creado con éxito");
      this.resetScheduleForm();
      if (this.schedFormCard) this.schedFormCard.style.display = "none";
      this.loadSchedules();
    } else if (resp.action === "update_scheduled_message") {
      this.showToast("Mensaje programado actualizado con éxito");
      this.resetScheduleForm();
      if (this.schedFormCard) this.schedFormCard.style.display = "none";
      this.loadSchedules();
    } else if (resp.action === "toggle_scheduled_message") {
      this.showToast("Estado de mensaje programado actualizado");
      this.loadSchedules();
    } else if (resp.action === "delete_scheduled_message") {
      this.showToast("Mensaje programado eliminado");
      this.loadSchedules();
    } else if (resp.action === "get_blocked_nodes") {
      this.renderBlockedNodes(data.blocked_nodes || []);
    } else if (resp.action === "get_auto_reported_nodes") {
      this.renderAutoReportedNodes(data.auto_reported_nodes || [], data.total);
    } else if (resp.action === "set_node_bot_ignored") {
      this.showToast(data.is_ignored ? `Nodo ${data.node_id} ignorado en el bot` : `Nodo ${data.node_id} deja de ser ignorado`);
      this.loadSecurityData();
    } else if (resp.action === "set_node_fw_blocked") {
      this.showToast(data.is_blocked ? `Nodo ${data.node_id} bloqueado en radio` : `Nodo ${data.node_id} desbloqueado en radio`);
      this.loadSecurityData();
    } else if (resp.action === "block_node_manual") {
      this.showToast("Nodo bloqueado correctamente");
      if (this.formManualBlock) this.formManualBlock.reset();
      this.loadSecurityData();
    } else if (resp.action === "unblock_node") {
      this.showToast("Nodo desbloqueado");
      this.loadSecurityData();
    } else if (resp.action === "get_abuse_logs") {
      this.renderAbuseLogs(data.logs || []);
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
        let hopBadgeText = "Señal RF";
        if (r.hops !== undefined && r.hops !== null) {
          hopBadgeText = (r.hops === 0) ? "Directo (RF)" : `${r.hops} ${r.hops === 1 ? "salto" : "saltos"} (RF)`;
        }
        routeBadge = `<span class="badge badge-ch0">${hopBadgeText}</span>`;
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
          <button class="btn-secondary card-action-btn" onclick="window.dashboard.requestTraceTo('${routerId}', this)">
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

    // 3. Filtro por Última Señal (Tiempo)
    if (this.currentTimeFilter && this.currentTimeFilter !== "all") {
      const nowMs = Date.now();
      const ONE_DAY = 24 * 3600 * 1000;
      const ONE_WEEK = 7 * ONE_DAY;
      const ONE_MONTH = 30 * ONE_DAY;

      nodes = nodes.filter(n => {
        const ms = this.parseDateTimestamp(n.last_heard || n.updated_at);
        if (this.currentTimeFilter === "24h") {
          return ms > 0 && (nowMs - ms) <= ONE_DAY;
        } else if (this.currentTimeFilter === "7d") {
          return ms > 0 && (nowMs - ms) <= ONE_WEEK;
        } else if (this.currentTimeFilter === "30d") {
          return ms > 0 && (nowMs - ms) <= ONE_MONTH;
        } else if (this.currentTimeFilter === "off_24h") {
          return ms === 0 || (nowMs - ms) > ONE_DAY;
        } else if (this.currentTimeFilter === "off_7d") {
          return ms === 0 || (nowMs - ms) > ONE_WEEK;
        } else if (this.currentTimeFilter === "off_30d") {
          return ms === 0 || (nowMs - ms) > ONE_MONTH;
        }
        return true;
      });
    }

    // 4. Filtro categoría
    if (this.currentNodeFilter === "rf") {
      nodes = nodes.filter(n => !n.via_mqtt);
    } else if (this.currentNodeFilter === "fav") {
      nodes = nodes.filter(n => n.is_favorite);
    } else if (this.currentNodeFilter === "battery") {
      nodes = nodes.filter(n => (n.battery !== undefined && n.battery !== null) || (n.voltage !== undefined && n.voltage !== null));
    }

    // 5. Ordenación Multidimensional
    const field = this.sortField;
    const dir = this.sortDirection === "asc" ? 1 : -1;

    nodes.sort((a, b) => {
      let valA = a[field];
      let valB = b[field];

      if (field === "is_favorite") {
        valA = valA ? 1 : 0;
        valB = valB ? 1 : 0;
      } else if (field === "battery") {
        const hasA = (a.battery !== undefined && a.battery !== null) || (a.voltage !== undefined && a.voltage !== null);
        const hasB = (b.battery !== undefined && b.battery !== null) || (b.voltage !== undefined && b.voltage !== null);
        if (hasA !== hasB) {
          // El que no tiene telemetría de batería va siempre al final
          return hasA ? -1 : 1;
        }
        valA = (a.battery !== undefined && a.battery !== null) ? Number(a.battery) : ((a.voltage !== undefined && a.voltage !== null) ? Number(a.voltage) : 0);
        valB = (b.battery !== undefined && b.battery !== null) ? Number(b.battery) : ((b.voltage !== undefined && b.voltage !== null) ? Number(b.voltage) : 0);
      } else if (field === "snr" || field === "hops" || field === "uptime") {
        const hasA = valA !== undefined && valA !== null;
        const hasB = valB !== undefined && valB !== null;
        if (hasA !== hasB) {
          // Los valores sin dato van siempre al final
          return hasA ? -1 : 1;
        }
        valA = hasA ? Number(valA) : 0;
        valB = hasB ? Number(valB) : 0;
      } else if (field === "last_heard" || field === "created_at") {
        const tA = this.parseDateTimestamp(valA || (field === "last_heard" ? a.updated_at : 0));
        const tB = this.parseDateTimestamp(valB || (field === "last_heard" ? b.updated_at : 0));
        const hasA = tA > 0;
        const hasB = tB > 0;
        if (hasA !== hasB) {
          // Nodos sin fecha registrada van siempre al final
          return hasA ? -1 : 1;
        }
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
      if (this.lblNodesCountInfo) this.lblNodesCountInfo.textContent = "Mostrando 0 de 0 nodos";
      if (this.lblNodesPage) this.lblNodesPage.textContent = "Página 1";
      if (this.btnNodesPrev) this.btnNodesPrev.disabled = true;
      if (this.btnNodesNext) this.btnNodesNext.disabled = true;
      return;
    }

    const totalFiltered = nodes.length;
    let pageNodes = nodes;

    if (this.nodesPageSize === "all") {
      pageNodes = nodes;
      if (this.lblNodesCountInfo) this.lblNodesCountInfo.textContent = `Mostrando todos (${totalFiltered} nodos)`;
      if (this.lblNodesPage) this.lblNodesPage.textContent = "Página 1 de 1";
      if (this.btnNodesPrev) this.btnNodesPrev.disabled = true;
      if (this.btnNodesNext) this.btnNodesNext.disabled = true;
    } else {
      const pageSize = Number(this.nodesPageSize) || 100;
      const totalPages = Math.max(1, Math.ceil(totalFiltered / pageSize));
      if (this.nodesPage > totalPages) this.nodesPage = totalPages;
      if (this.nodesPage < 1) this.nodesPage = 1;

      const startIdx = (this.nodesPage - 1) * pageSize;
      const endIdx = Math.min(startIdx + pageSize, totalFiltered);
      pageNodes = nodes.slice(startIdx, endIdx);

      if (this.lblNodesCountInfo) this.lblNodesCountInfo.textContent = `Mostrando ${startIdx + 1}-${endIdx} de ${totalFiltered} nodos`;
      if (this.lblNodesPage) this.lblNodesPage.textContent = `Página ${this.nodesPage} de ${totalPages}`;
      if (this.btnNodesPrev) this.btnNodesPrev.disabled = this.nodesPage <= 1;
      if (this.btnNodesNext) this.btnNodesNext.disabled = this.nodesPage >= totalPages;
    }

    this.nodesTbody.innerHTML = pageNodes.map(n => {
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
  // Módulo 04: Programación de Mensajes y Difusión
  // ==========================================================================
  resetScheduleForm() {
    if (this.formCreateSched) this.formCreateSched.reset();
    if (this.schedEditId) this.schedEditId.value = "";
    if (this.schedFormTitle) this.schedFormTitle.textContent = "Nuevo Mensaje Programado";
    if (this.btnSubmitSched) this.btnSubmitSched.textContent = "Guardar y Programar";
    if (this.schedChAll) this.schedChAll.checked = true;
    document.querySelectorAll(".sched-ch-item").forEach(cb => {
      cb.checked = true;
      cb.disabled = true;
    });
    if (this.schedValWrap) this.schedValWrap.style.display = "block";
    if (this.schedPeriodType) this.schedPeriodType.value = "hours";
    if (this.schedPeriodVal) this.schedPeriodVal.value = 6;
    if (this.schedStartAt) this.schedStartAt.value = "";
    if (this.schedMsgCharcount) this.schedMsgCharcount.textContent = "0 / 500 caracteres";
    if (this.schedMsgPartscount) {
      this.schedMsgPartscount.textContent = "1 parte LoRa (~200 bytes)";
      this.schedMsgPartscount.style.color = "var(--primary)";
    }
  }

  handleCreateSchedule() {
    if (!this.schedMsgText) return;
    const text = this.schedMsgText.value.trim();
    if (!text) {
      this.showToast("Debes escribir un mensaje o comando para programar", "warning");
      return;
    }

    let channels = "all";
    if (this.schedChAll && !this.schedChAll.checked) {
      const selected = Array.from(document.querySelectorAll(".sched-ch-item:checked")).map(cb => parseInt(cb.value, 10));
      channels = selected.length > 0 ? selected : [0];
    }

    const pType = this.schedPeriodType ? this.schedPeriodType.value : "hours";
    const pVal = this.schedPeriodVal ? Math.max(1, parseInt(this.schedPeriodVal.value, 10) || 1) : 1;
    const startAt = (this.schedStartAt && this.schedStartAt.value) ? this.schedStartAt.value : null;
    const editId = this.schedEditId ? this.schedEditId.value : "";

    if (editId) {
      this.sendAction("update_scheduled_message", {
        id: parseInt(editId, 10),
        data: {
          message: text,
          channels: channels,
          period_type: pType,
          period_value: pVal,
          start_at: startAt,
          next_run_at: startAt,
        }
      });
    } else {
      this.sendAction("create_scheduled_message", {
        message: text,
        channels: channels,
        period_type: pType,
        period_value: pVal,
        start_at: startAt,
        enabled: true,
      });
    }
  }

  editSchedule(id) {
    const m = (this.scheduledMessages || []).find(item => item.id === id);
    if (!m) {
      this.showToast("No se encontró la programación", "error");
      return;
    }

    if (this.schedEditId) this.schedEditId.value = m.id;
    if (this.schedFormTitle) this.schedFormTitle.textContent = `Editar Programación #${m.id}`;
    if (this.btnSubmitSched) this.btnSubmitSched.textContent = "Guardar Cambios";

    if (this.schedMsgText) {
      this.schedMsgText.value = m.message || "";
      this.schedMsgText.dispatchEvent(new Event("input"));
    }

    // Configurar selección de canales
    const isAll = (m.channels === "all" || m.channels === "*" || m.channels === '["all"]');
    if (this.schedChAll) {
      this.schedChAll.checked = isAll;
    }

    let chList = [];
    if (!isAll) {
      try {
        chList = typeof m.channels === "string" ? JSON.parse(m.channels) : m.channels;
        if (!Array.isArray(chList)) chList = [parseInt(m.channels, 10)];
      } catch (e) {
        chList = String(m.channels).split(",").map(c => parseInt(c.trim(), 10)).filter(c => !isNaN(c));
      }
    }

    document.querySelectorAll(".sched-ch-item").forEach(cb => {
      const val = parseInt(cb.value, 10);
      cb.disabled = isAll;
      cb.checked = isAll || chList.includes(val);
    });

    // Periodicidad
    if (this.schedPeriodType) {
      this.schedPeriodType.value = m.period_type || "hours";
    }
    if (this.schedValWrap) {
      this.schedValWrap.style.display = (m.period_type === "once") ? "none" : "block";
    }
    if (this.schedPeriodVal) {
      this.schedPeriodVal.value = m.period_value || 1;
    }

    // Fecha/Hora de próximo disparo
    if (this.schedStartAt) {
      const targetDateStr = m.next_run_at || m.start_at || "";
      if (targetDateStr) {
        try {
          const cleanIso = targetDateStr.replace(" ", "T").slice(0, 16);
          this.schedStartAt.value = cleanIso;
        } catch (e) {
          this.schedStartAt.value = "";
        }
      } else {
        this.schedStartAt.value = "";
      }
    }

    if (this.schedFormCard) {
      this.schedFormCard.style.display = "block";
      this.schedFormCard.scrollIntoView({ behavior: "smooth" });
    }
  }

  renderScheduledMessages(messages) {
    this.scheduledMessages = messages || [];
    if (!this.schedulesTbody) return;

    const activeCount = this.scheduledMessages.filter(m => m.enabled).length;
    if (this.countScheds) this.countScheds.textContent = activeCount;

    if (this.scheduledMessages.length === 0) {
      this.schedulesTbody.innerHTML = `
        <tr><td colspan="7" style="text-align: center; color: var(--text-dim); padding: 20px;">No hay mensajes programados actualmente.</td></tr>
      `;
      return;
    }

    this.schedulesTbody.innerHTML = this.scheduledMessages.map(m => {
      const isEnabled = !!m.enabled;
      let chLabel = "Todos";
      if (m.channels !== "all" && m.channels !== "*") {
        try {
          const parsed = typeof m.channels === "string" ? JSON.parse(m.channels) : m.channels;
          if (Array.isArray(parsed)) chLabel = parsed.map(c => `Ch ${c}`).join(", ");
          else chLabel = `Ch ${m.channels}`;
        } catch (e) {
          chLabel = String(m.channels);
        }
      }

      let freqStr = "";
      if (m.period_type === "hours") freqStr = `Cada ${m.period_value} h`;
      else if (m.period_type === "days") freqStr = `Cada ${m.period_value} días`;
      else freqStr = "Una sola vez";

      const lastSent = m.last_sent_at ? this.formatRelativeOrDate(m.last_sent_at) : "Nunca";
      const nextRun = m.next_run_at ? this.formatRelativeOrDate(m.next_run_at) : (isEnabled ? "Inmediato" : "Pausado");

      const isCmd = (m.message || "").trim().startsWith("/") || (m.message || "").trim().startsWith("!");
      const msgDisplay = isCmd
        ? `<span class="badge" style="background: var(--warning-bg); color: var(--warning); margin-right: 6px; font-weight: 700;">⚡ COMANDO</span><code style="color: var(--warning); font-weight: 600; font-size: 0.9rem;">${this.escapeHtml(m.message)}</code>`
        : `<strong>${this.escapeHtml(m.message)}</strong>`;

      return `
        <tr>
          <td>
            <button class="btn-secondary" style="padding: 2px 8px; font-size: 0.75rem; background: ${isEnabled ? "var(--success-bg)" : "var(--danger-bg)"}; color: ${isEnabled ? "var(--success)" : "var(--danger)"};" onclick="window.dashboard.toggleSchedule(${m.id}, ${!isEnabled})">
              ${isEnabled ? "ACTIVO" : "PAUSADO"}
            </button>
          </td>
          <td>
            ${msgDisplay}
          </td>
          <td><span class="badge" style="background: var(--primary-bg); color: var(--primary);">${this.escapeHtml(chLabel)}</span></td>
          <td>${this.escapeHtml(freqStr)}</td>
          <td style="font-size: 0.8rem; color: var(--text-muted);">${lastSent}</td>
          <td style="font-size: 0.8rem; color: var(--primary); font-weight: 600;">${nextRun}</td>
          <td>
            <div style="display: flex; gap: 6px; align-items: center;">
              <button class="btn-secondary" style="padding: 3px 8px; font-size: 0.75rem; color: var(--primary);" title="Editar Programación" onclick="window.dashboard.editSchedule(${m.id})">
                ✏️ Editar
              </button>
              <button class="btn-secondary" style="padding: 3px 8px; font-size: 0.75rem; color: var(--danger);" title="Eliminar Programación" onclick="window.dashboard.deleteSchedule(${m.id})">
                🗑️ Borrar
              </button>
            </div>
          </td>
        </tr>
      `;
    }).join("");
  }

  toggleSchedule(id, enable) {
    this.sendAction("toggle_scheduled_message", { id: id, enabled: enable });
  }

  deleteSchedule(id) {
    if (confirm("¿Estás seguro de que deseas eliminar este mensaje programado?")) {
      this.sendAction("delete_scheduled_message", { id: id });
    }
  }

  // ==========================================================================
  // Módulo 06: Seguridad, Anti-Abuso y Bloqueos
  // ==========================================================================
  handleManualBlock() {
    if (!this.blockNodeId) return;
    const nodeId = this.blockNodeId.value.trim();
    if (!nodeId) {
      this.showToast("Debes especificar un ID o nombre de nodo", "warning");
      return;
    }

    const reason = this.blockReason ? this.blockReason.value.trim() : "Bloqueo manual administrativo";
    const duration = this.blockDuration ? this.blockDuration.value : "permanent";

    let expiresAt = null;
    const now = Date.now();
    if (duration === "1h") expiresAt = new Date(now + 3600 * 1000).toISOString();
    else if (duration === "24h") expiresAt = new Date(now + 24 * 3600 * 1000).toISOString();
    else if (duration === "7d") expiresAt = new Date(now + 7 * 24 * 3600 * 1000).toISOString();

    this.sendAction("block_node_manual", {
      node_id: nodeId,
      reason: reason,
      expires_at: expiresAt,
    });
  }

  loadAutoReportedNodes() {
    const reason = (this.filterAutoreportReason && this.filterAutoreportReason.value !== "all") ? this.filterAutoreportReason.value : null;
    this.sendAction("get_auto_reported_nodes", { reason_code: reason });
  }

  sortAutoReported(col) {
    if (!this.autoReportSortCol) {
      this.autoReportSortCol = "last_detected_at";
      this.autoReportSortDir = "desc";
    }
    if (this.autoReportSortCol === col) {
      this.autoReportSortDir = this.autoReportSortDir === "asc" ? "desc" : "asc";
    } else {
      this.autoReportSortCol = col;
      this.autoReportSortDir = (col === "event_count" || col === "last_detected_at") ? "desc" : "asc";
    }
    this.renderAutoReportedNodes(this.autoReportedNodes, this._totalAutoReported);
  }

  renderAutoReportedNodes(nodes, total) {
    if (nodes) this.autoReportedNodes = nodes;
    if (!this.autoReportedTbody) return;

    if (!this.autoReportSortCol) {
      this.autoReportSortCol = "last_detected_at";
      this.autoReportSortDir = "desc";
    }

    if (total !== undefined && total !== null) {
      this._totalAutoReported = total;
    } else if (this._totalAutoReported === undefined) {
      this._totalAutoReported = (this.autoReportedNodes || []).length;
    }

    const count = this._totalAutoReported;
    if (this.countReportedBadge) this.countReportedBadge.textContent = count;
    if (this.countBlocked) this.countBlocked.textContent = count;

    // Actualizar iconos indicadores de ordenación
    ["reason_code", "name", "event_count", "last_detected_at"].forEach(c => {
      const el = document.getElementById("sort-icon-" + c);
      if (el) {
        el.textContent = (this.autoReportSortCol === c) ? (this.autoReportSortDir === "asc" ? " ▲" : " ▼") : "";
      }
    });

    if (!this.autoReportedNodes || this.autoReportedNodes.length === 0) {
      this.autoReportedTbody.innerHTML = `
        <tr><td colspan="7" style="text-align: center; color: var(--text-dim); padding: 20px;">No hay incidencias de mala praxis registradas.</td></tr>
      `;
      return;
    }

    // Ordenar nodos según columna activa
    const sorted = [...this.autoReportedNodes].sort((a, b) => {
      let vA, vB;
      if (this.autoReportSortCol === "name") {
        vA = (a.name || a.short_name || a.node_id || "").toLowerCase();
        vB = (b.name || b.short_name || b.node_id || "").toLowerCase();
      } else if (this.autoReportSortCol === "event_count") {
        vA = Number(a.event_count || 0);
        vB = Number(b.event_count || 0);
      } else if (this.autoReportSortCol === "reason_code") {
        vA = (a.reason_code || "").toLowerCase();
        vB = (b.reason_code || "").toLowerCase();
      } else {
        vA = a.last_detected_at || "";
        vB = b.last_detected_at || "";
      }
      if (vA < vB) return this.autoReportSortDir === "asc" ? -1 : 1;
      if (vA > vB) return this.autoReportSortDir === "asc" ? 1 : -1;
      return 0;
    });

    const reasonBadges = {
      "EXCESSIVE_HOPS": { icon: "🔀", label: "Saltos Excesivos", bg: "var(--danger-bg)", color: "var(--danger)" },
      "FAST_TELEMETRY": { icon: "⚡", label: "Telemetría Rápida", bg: "var(--warning-bg)", color: "var(--warning)" },
      "FAST_POSITION": { icon: "📍", label: "Posición GPS Rápida", bg: "var(--warning-bg)", color: "var(--warning)" },
      "FAST_NODEINFO": { icon: "👥", label: "NodeInfo Rápido", bg: "var(--primary-bg)", color: "var(--primary)" },
      "FAST_ENVIRONMENTAL": { icon: "🌡️", label: "Sensores Clima", bg: "var(--warning-bg)", color: "var(--warning)" },
      "COMMAND_SPAM": { icon: "🛑", label: "Spam Comandos", bg: "var(--danger-bg)", color: "var(--danger)" },
    };

    this.autoReportedTbody.innerHTML = sorted.map(n => {
      const bInfo = reasonBadges[n.reason_code] || { icon: "⚠️", label: n.reason_code || "Alerta", bg: "var(--bg-input)", color: "var(--text-muted)" };
      const badgeHtml = `<span class="badge" style="background: ${bInfo.bg}; color: ${bInfo.color}; font-size: 0.75rem;">${bInfo.icon} ${bInfo.label}</span>`;
      
      const lastSeenStr = this.formatRelativeOrDate(n.last_detected_at);
      const isIgnored = !!n.is_ignored_bot;
      const isFwBlocked = !!n.is_blocked_fw;

      let statusBadges = [];
      if (isIgnored) statusBadges.push(`<span class="badge" style="background: var(--danger-bg); color: var(--danger);">Ignorado Bot</span>`);
      if (isFwBlocked) statusBadges.push(`<span class="badge" style="background: var(--warning-bg); color: var(--warning);">Bloqueado Radio</span>`);
      if (statusBadges.length === 0) statusBadges.push(`<span class="badge" style="background: var(--bg-input); color: var(--text-dim);">Vigilado</span>`);

      return `
        <tr>
          <td>${badgeHtml}</td>
          <td>
            <strong>${this.escapeHtml(n.name || n.short_name || n.node_id)}</strong>
            <div style="font-family: monospace; font-size: 0.75rem; color: var(--text-dim);">${this.escapeHtml(n.node_id)}</div>
          </td>
          <td style="font-size: 0.85rem; color: var(--text-muted);">${this.escapeHtml(n.reason_desc || "--")}</td>
          <td style="text-align: center; font-weight: 700; color: ${n.event_count > 5 ? "var(--danger)" : "var(--primary)"};">${n.event_count}</td>
          <td style="font-size: 0.8rem; color: var(--text-dim);">${lastSeenStr}</td>
          <td><div style="display: flex; gap: 4px; flex-wrap: wrap;">${statusBadges.join("")}</div></td>
          <td>
            <div style="display: flex; gap: 6px; justify-content: center; flex-wrap: wrap;">
              <button class="btn-secondary" style="padding: 3px 8px; font-size: 0.75rem; ${isIgnored ? "color: var(--success);" : "color: var(--danger);"}" onclick="window.dashboard.toggleIgnoreNode('${n.node_id}', ${!isIgnored})">
                ${isIgnored ? "✅ Atender" : "🚫 Ignorar"}
              </button>
              <button class="btn-secondary" style="padding: 3px 8px; font-size: 0.75rem; ${isFwBlocked ? "color: var(--success);" : "color: var(--warning);"}" onclick="window.dashboard.toggleFwBlockNode('${n.node_id}', ${!isFwBlocked})">
                ${isFwBlocked ? "🔓 Desbloquear" : "🔒 Bloquear Radio"}
              </button>
            </div>
          </td>
        </tr>
      `;
    }).join("");
  }

  toggleIgnoreNode(nodeId, isIgnored) {
    this.sendAction("set_node_bot_ignored", { node_id: nodeId, is_ignored: isIgnored });
  }

  toggleFwBlockNode(nodeId, isBlocked) {
    this.sendAction("set_node_fw_blocked", { node_id: nodeId, is_blocked: isBlocked });
  }

  renderBlockedNodes(nodes) {
    this.blockedNodes = nodes || [];
    if (!this.blockedNodesTbody) return;

    const activeCount = this.blockedNodes.filter(n => n.active).length;
    if (this.countBlocked) this.countBlocked.textContent = activeCount;

    if (this.blockedNodes.length === 0) {
      this.blockedNodesTbody.innerHTML = `
        <tr><td colspan="6" style="text-align: center; color: var(--text-dim); padding: 20px;">No hay nodos bloqueados actualmente.</td></tr>
      `;
      return;
    }

    this.blockedNodesTbody.innerHTML = this.blockedNodes.map(n => {
      const isActive = !!n.active;
      const typeBadge = n.block_type === "auto"
        ? `<span class="badge" style="background: var(--warning-bg); color: var(--warning);">AUTO</span>`
        : `<span class="badge" style="background: var(--danger-bg); color: var(--danger);">MANUAL</span>`;
      
      const createdStr = this.formatRelativeOrDate(n.created_at);
      const expiresStr = n.expires_at ? this.formatRelativeOrDate(n.expires_at) : `<span style="color: var(--text-dim);">Permanente</span>`;

      return `
        <tr>
          <td>${typeBadge}</td>
          <td>
            <strong>${this.escapeHtml(n.node_name || n.node_id)}</strong>
            <div style="font-family: monospace; font-size: 0.75rem; color: var(--text-dim);">${this.escapeHtml(n.node_id)}</div>
          </td>
          <td style="font-size: 0.85rem; color: var(--text-muted);">${this.escapeHtml(n.reason || "--")}</td>
          <td style="font-size: 0.8rem; color: var(--text-dim);">${createdStr}</td>
          <td style="font-size: 0.8rem; color: var(--primary);">${expiresStr}</td>
          <td>
            ${isActive ? `
              <button class="btn-secondary" style="padding: 3px 8px; font-size: 0.75rem; color: var(--success);" onclick="window.dashboard.unblockNode('${n.node_id}')">
                Desbloquear
              </button>
            ` : `<span style="color: var(--text-dim); font-size: 0.8rem;">Inactivo</span>`}
          </td>
        </tr>
      `;
    }).join("");
  }

  unblockNode(nodeId) {
    this.sendAction("unblock_node", { node_id: nodeId });
  }

  renderAbuseLogs(logs) {
    this.abuseLogs = logs || [];
    if (!this.abuseLogsTbody) return;

    if (this.abuseLogs.length === 0) {
      this.abuseLogsTbody.innerHTML = `
        <tr><td colspan="5" style="text-align: center; color: var(--text-dim); padding: 20px;">No hay registros de abusos o saturación recientes.</td></tr>
      `;
      return;
    }

    this.abuseLogsTbody.innerHTML = this.abuseLogs.map(l => {
      const timeStr = l.created_at ? l.created_at.replace("T", " ").substring(0, 19) : "--";
      return `
        <tr>
          <td style="font-size: 0.8rem; color: var(--text-muted);">${timeStr}</td>
          <td style="font-family: monospace; font-size: 0.85rem;">${this.escapeHtml(l.node_id)}</td>
          <td><span class="badge" style="background: var(--danger-bg); color: var(--danger);">${this.escapeHtml(l.action_taken || "bloqueo")}</span></td>
          <td>${l.command ? `<code style="color: var(--warning);">/${this.escapeHtml(l.command)}</code>` : "--"}</td>
          <td style="font-size: 0.85rem; color: var(--text-muted);">${this.escapeHtml(l.reason || "--")}</td>
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
  // Guía Interactiva de Comandos (Pestaña 9)
  // ==========================================================================
  renderCommandsGuide(filterText = "") {
    if (!this.commandsContainer) return;

    const query = (filterText || "").toLowerCase().trim();

    const categories = [
      {
        title: "🌦️ Meteorología, Marítimo y Naturaleza",
        commands: [
          {
            name: "/tiempo",
            alias: "/weather",
            inGroup: true,
            desc: "Predicción meteorológica del día actual para la provincia o municipio configurado.",
            usage: "/tiempo",
            examples: ["/tiempo", "/tiempo real", "/tiempo sevilla"],
          },
          {
            name: "/prevision",
            inGroup: true,
            desc: "Previsión meteorológica por periodos: 3 días (defecto), mañana, 1-7 días o 1-12 horas.",
            usage: "/prevision [mañana | X dias | X horas]",
            examples: ["/prevision", "/prevision mañana", "/prevision 4 dias", "/prevision 6 horas"],
          },
          {
            name: "/marea",
            inGroup: true,
            desc: "Pleamares y bajamares del día. Con /marea mar consulta el boletín marítimo costero de Cádiz.",
            usage: "/marea [mar | costa]",
            examples: ["/marea", "/marea mar"],
          },
          {
            name: "/avisos",
            inGroup: true,
            desc: "Alertas meteorológicas oficiales vigentes emitidas por Meteoalerta / AEMET con color y vigencia.",
            usage: "/avisos",
            examples: ["/avisos"],
          },
          {
            name: "/sol",
            inGroup: true,
            desc: "Horas de orto (amanecer), ocaso (atardecer) y duración solar del día (cálculo 100% offline).",
            usage: "/sol",
            examples: ["/sol"],
          },
          {
            name: "/luna",
            inGroup: true,
            desc: "Fase lunar actual, porcentaje de iluminación y próximas fases lunares (100% offline).",
            usage: "/luna",
            examples: ["/luna"],
          },
          {
            name: "/boletin",
            inGroup: true,
            desc: "Resumen consolidado en 2 partes: Sol, Luna, Tiempo Provincial, Mareas costeras y Avisos.",
            usage: "/boletin [matinal | vespertino]",
            examples: ["/boletin", "/boletin matinal", "/boletin vespertino"],
          },
          {
            name: "/maremoto",
            inGroup: true,
            desc: "Contador histórico y efeméride del maremoto de 1755 en Chipiona y costas de Cádiz.",
            usage: "/maremoto",
            examples: ["/maremoto"],
          },
        ],
      },
      {
        title: "📻 Red Meshtastic, Repetidores y Enlaces",
        commands: [
          {
            name: "/ping",
            alias: "/test",
            inGroup: true,
            desc: "Comprueba recepción, SNR, RSSI y número de saltos (hops) directos o repetidos.",
            usage: "/ping",
            examples: ["/ping", "/test"],
          },
          {
            name: "/routers",
            alias: "/repetidores",
            inGroup: true,
            desc: "Estado de repetidores y routers clave de la malla (tiempo desde último contacto, saltos y SNR).",
            usage: "/routers",
            examples: ["/routers", "/repetidores"],
          },
          {
            name: "/snr",
            inGroup: true,
            desc: "Calidad de señal del nodo pasarela/base (RAU0) y media general de SNR de la malla RF.",
            usage: "/snr",
            examples: ["/snr"],
          },
          {
            name: "/nodos",
            inGroup: true,
            desc: "Conteo total de nodos descubiertos en la base de datos (RF, MQTT y activos en las últimas 24h).",
            usage: "/nodos",
            examples: ["/nodos"],
          },
        ],
      },
      {
        title: "🤖 Asistente de IA y Comunidad",
        commands: [
          {
            name: "/ia",
            inGroup: true,
            desc: "Asistente de emergencias impulsado por IA mínima (RAG) con cola secuencial y memoria por nodo.",
            usage: "/ia <pregunta> | /ia reset",
            examples: ["/ia primeros auxilios", "/ia reset"],
          },
          {
            name: "/chiste",
            inGroup: true,
            desc: "Cuenta un chiste aleatorio del repositorio o añade una nueva propuesta comunitaria.",
            usage: "/chiste | /chiste add <texto>",
            examples: ["/chiste", "/chiste add ¿Qué le dice un bit a otro? Nos vemos en el bus."],
          },
          {
            name: "/encuesta",
            inGroup: true,
            desc: "Sistema de encuestas y votaciones comunitarias por radio en la malla LoRa.",
            usage: "/encuesta [nueva | voto | ver | lista | cerrar]",
            examples: ["/encuesta ver", "/encuesta voto 1", "/encuesta nueva ¿Quedada? | Sí | No"],
          },
          {
            name: "/dado",
            inGroup: true,
            desc: "Tirada de dados aleatorios (1d6 por defecto, N caras o formato NdM).",
            usage: "/dado [N | NdM]",
            examples: ["/dado", "/dado 20", "/dado 2d6"],
          },
          {
            name: "/bola8",
            alias: "/8ball",
            inGroup: true,
            desc: "Bola mágica 8 para respuestas aleatorias de sí o no.",
            usage: "/bola8 <pregunta>",
            examples: ["/bola8 ¿Lloverá mañana?"],
          },
        ],
      },
      {
        title: "⚙️ Sistema, Telemetría y Bot",
        commands: [
          {
            name: "/help",
            inGroup: false,
            desc: "Muestra la lista de comandos disponibles o la ayuda detallada de un comando específico.",
            usage: "/help [comando]",
            examples: ["/help", "/help prevision", "/help marea"],
          },
          {
            name: "/about",
            inGroup: false,
            desc: "Información técnica sobre el bot, hardware, software y autor.",
            usage: "/about",
            examples: ["/about"],
          },
          {
            name: "/estado",
            alias: "/status, /salud, /bot, /telemetria",
            inGroup: true,
            desc: "Telemetría hardware de la Raspberry Pi: temperatura CPU, carga, memoria RAM, disco y uptime.",
            usage: "/estado",
            examples: ["/estado", "/salud", "/bot"],
          },
          {
            name: "/uptime",
            inGroup: false,
            desc: "Tiempo de encendido continuo y funcionamiento ininterrumpido del bot.",
            usage: "/uptime",
            examples: ["/uptime"],
          },
        ],
      },
    ];

    let html = "";
    let totalFound = 0;

    categories.forEach(cat => {
      const filtered = cat.commands.filter(c => {
        if (!query) return true;
        return (
          c.name.toLowerCase().includes(query) ||
          (c.alias && c.alias.toLowerCase().includes(query)) ||
          c.desc.toLowerCase().includes(query) ||
          c.usage.toLowerCase().includes(query) ||
          (c.examples && c.examples.some(ex => ex.toLowerCase().includes(query)))
        );
      });

      if (filtered.length > 0) {
        totalFound += filtered.length;
        html += `
          <div class="commands-category">
            <div class="commands-category-title">${cat.title} (${filtered.length})</div>
            <div class="commands-grid">
        `;

        filtered.forEach(c => {
          const badgeClass = c.inGroup ? "badge-channel" : "badge-dm";
          const badgeText = c.inGroup ? "📢 Canal y Privado" : "💬 Solo Privado (DM)";
          const aliasHtml = c.alias ? `<span style="font-size: 0.75rem; color: var(--text-dim); margin-left: 6px;">alias: ${this.escapeHtml(c.alias)}</span>` : "";

          html += `
            <div class="command-card">
              <div>
                <div class="command-header">
                  <div style="display: flex; align-items: center; flex-wrap: wrap;">
                    <span class="command-name" title="Haz clic para probar en el chat" onclick="dashboard.selectCommandForChat('${c.name}')">${c.name}</span>
                    ${aliasHtml}
                  </div>
                  <span class="command-badge ${badgeClass}">${badgeText}</span>
                </div>
                <div class="command-desc" style="margin-top: 8px;">
                  ${this.escapeHtml(c.desc)}
                </div>
              </div>

              <div>
                <div style="font-size: 0.75rem; color: var(--text-muted); margin-bottom: 4px;">Sintaxis y Ejemplos:</div>
                <div class="command-usage-box" title="Haz clic para copiar" onclick="dashboard.copyCommandToClipboard('${c.usage}')">
                  <span>${this.escapeHtml(c.usage)}</span>
                  <button class="btn-try-cmd" title="Probar en el chat" onclick="event.stopPropagation(); dashboard.selectCommandForChat('${c.name}')">💬</button>
                </div>
                ${
                  c.examples && c.examples.length > 1
                    ? `<div style="display: flex; flex-wrap: wrap; gap: 4px; margin-top: 6px;">
                        ${c.examples.map(ex => `<button class="filter-chip" style="font-size: 0.72rem; padding: 2px 6px;" onclick="dashboard.selectCommandForChat('${ex}')">${this.escapeHtml(ex)}</button>`).join("")}
                       </div>`
                    : ""
                }
              </div>
            </div>
          `;
        });

        html += `
            </div>
          </div>
        `;
      }
    });

    if (totalFound === 0) {
      html = `
        <div class="card" style="text-align: center; padding: 40px 20px; color: var(--text-muted);">
          <div style="font-size: 2rem; margin-bottom: 8px;">🔍</div>
          <p>No se encontraron comandos que coincidan con <strong>"${this.escapeHtml(query)}"</strong>.</p>
          <button class="btn btn-secondary" style="margin-top: 10px;" onclick="document.getElementById('commands-search-input').value = ''; dashboard.renderCommandsGuide('');">Limpiar filtro</button>
        </div>
      `;
    }

    this.commandsContainer.innerHTML = html;
  }

  selectCommandForChat(cmdText) {
    if (!this.chatText) return;
    this.switchTab("chat");
    this.chatText.value = cmdText;
    this.chatText.focus();
    this.showToast(`Comando "${cmdText}" insertado en el chat`, "info");
  }

  copyCommandToClipboard(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(() => {
        this.showToast(`Copiado: ${text}`, "info");
      }).catch(() => {
        this.selectCommandForChat(text);
      });
    } else {
      this.selectCommandForChat(text);
    }
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
