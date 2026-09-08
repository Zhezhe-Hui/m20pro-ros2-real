    // FRP routes /video1 and /video2 on the public origin. Any private/LAN
    // hostname (tablet on the dog WiFi AP subnet, wired LAN, localhost)
    // connects directly to the MediaMTX listener on the robot.
    function isPrivateCameraHost(hostname) {
      if (hostname === "localhost" || hostname === "127.0.0.1") return true;
      const m = String(hostname).match(/^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/);
      if (!m) return false;
      const a = Number(m[1]);
      const b = Number(m[2]);
      return a === 10 || (a === 192 && b === 168) || (a === 172 && b >= 16 && b <= 31) || a === 169;
    }
    const directCameraHost = isPrivateCameraHost(window.location.hostname);
    const cameraStreamOrigin = directCameraHost
      ? `${window.location.protocol}//${window.location.hostname}:8888`
      : window.location.origin;
    let hlsLibraryPromise = null;
    function ensureHlsLibrary() {
      if (window.Hls) return Promise.resolve(window.Hls);
      if (hlsLibraryPromise) return hlsLibraryPromise;
      hlsLibraryPromise = new Promise(resolve => {
        const script = document.createElement("script");
        script.src = `${cameraStreamOrigin}/video1/hls.min.js`;
        script.addEventListener("load", () => {
          const hls = window.Hls || null;
          if (!hls) hlsLibraryPromise = null;
          resolve(hls);
        }, {once: true});
        script.addEventListener("error", () => {
          hlsLibraryPromise = null;
          resolve(null);
        }, {once: true});
        document.head.appendChild(script);
      });
      return hlsLibraryPromise;
    }
    for (const [cameraName, pathName] of [["front", "video1"], ["rear", "video2"]]) {
      const video = document.getElementById(`${cameraName}Video`);
      if (video) video.dataset.src = `${cameraStreamOrigin}/${pathName}/index.m3u8`;
    }
    // Public viewers play through the cloud SRS WebRTC relay. The dashboard
    // API starts the RTMP push on demand and relays the SDP exchange, so the
    // browser never needs direct access to the SRS API port.
    const remoteStreamEnabled = !directCameraHost;

    const canvas = document.getElementById("mapCanvas");
    const ctx = canvas.getContext("2d");
    const state = {
      map: null,
      spatialMap: null,
      latest: null,
      selectedMapId: null,
      workingMapId: null,
      effectiveMapId: null,
      maps: [],
      annotations: [],
      tasks: [],
      selectedMapStatus: null,
      markDraft: null,
      markDraftSource: "map_click",
      editingAnnotationId: null,
      localizeDraft: null,
      markPointer: null,
      panPointer: null,
      rotatePointer: null,
      robotDisplayPose: null,
      mapViewMode: "3d",
      view: {
        zoom: 1,
        panX: 0,
        panY: 0,
        yaw: -Math.PI / 4,
        pitch: Math.PI / 5.2,
        panMode: false,
        sliceZ: null
      },
      floors: [],
      floorsSignature: null,
      followRobot: true,
      preflight: null,
      lastRelocalizationStamp: null,
      relocalizationApiLogUntil: 0,
      activeTaskLogUntil: 0,
      lastTasksRefreshAt: 0,
      lastTasksPayload: null,
      loadingTasks: false,
      lastRecordingRefreshAt: 0,
      scanOverlay: true,
      workPointerMode: "localize",
      localizationPopoverOpen: false,
      mapSwitching: false,
      liveRequestInFlight: false,
      multiFloor: null,
      floorRoutes: {routes: [], candidates: [], maps: []},
      dddmrMapAssets: null,
      lastDddmrMapAssetsRefreshAt: 0,
      loadingDddmrMapAssets: false,
      dddmrFieldTest: null,
      loadingDddmrFieldTest: false,
      dddmrFieldTestMode: null,
      dddmrAssetDraft: null,
      taskDraftIds: [],
      crossFloorDraftIds: [],
      annotationQuery: "",
      annotationPage: 0,
      taskQuery: "",
      taskPage: 0,
      taskPointQuery: "",
      crossFloorPointQuery: "",
      radarResults: [],
      radarResultQuery: "",
      radarResultMode: "",
      radarResultPage: 0,
      radarResultTotal: 0,
      lastRadarResultsRefreshAt: 0,
      loadingRadarResults: false,
      yoloControlBusy: false,
      yoloLiveRequestInFlight: false,
      sessionId: null,
      mappingSession: null,
      latestMappingSession: null,
      mappingMapNameTouched: false,
      mappingCompletedStages: [],
      teleop: {
        sessionId: null,
        sequence: 0,
        axes: {linear_x: 0, linear_y: 0, angular_z: 0},
        pointers: new Map(),
        keys: new Map(),
        heartbeatTimer: null,
        requestInFlight: false,
        pendingCommand: false,
        releasing: false
      },
      floorControlsInitialized: false,
      lastMultiFloorRefreshAt: 0,
    };
    window.m20proDebug = {
      snapshot() {
        return {
          latest: state.latest,
          spatialMap: state.spatialMap,
          selectedMapId: state.selectedMapId,
          workingMapId: state.workingMapId,
          effectiveMapId: state.effectiveMapId,
          maps: state.maps,
          annotations: state.annotations,
          tasks: state.tasks,
          selectedMapStatus: state.selectedMapStatus,
          lastTasksPayload: state.lastTasksPayload,
          preflight: state.preflight,
          followRobot: state.followRobot,
          multiFloor: state.multiFloor,
          floorRoutes: state.floorRoutes,
          dddmrMapAssets: state.dddmrMapAssets,
          dddmrFieldTest: state.dddmrFieldTest,
          dddmrFieldTestMode: state.dddmrFieldTestMode,
          dddmrAssetDraft: state.dddmrAssetDraft,
          taskDraftIds: state.taskDraftIds.slice(),
          crossFloorDraftIds: state.crossFloorDraftIds.slice(),
          radarResults: state.radarResults,
          view: state.view
        };
      }
    };
    const manualPointTypeNames = {
      transition: "过渡点",
      task: "任务点",
      charge: "充电点"
    };
    const manualPointTypeColors = {
      transition: "#b45309",
      task: "#0f6bff",
      charge: "#15803d"
    };
    const manualTypeByUiType = {
      patrol: "task",
      task: "task",
      stair_entry: "transition",
      stair_switch: "transition",
      stair_exit: "transition",
      transition: "transition",
      charge: "charge"
    };
    const defaultByManualType = {
      transition: { dwell: 0, gait: 12, speed: 1 },
      task: { dwell: 5, gait: 12, speed: 1 },
      charge: { dwell: 0, gait: 12, speed: 1 }
    };
    const defaultGaitByUiType = {stair_entry: 14, stair_exit: 12, stair_switch: 12};
    const typeNames = {
      patrol: "任务点",
      stair_entry: "爬楼梯点",
      stair_switch: "楼层切换点",
      stair_exit: "出楼梯点",
      charge: "充电点",
      transition: "过渡点"
    };
    const typeColors = {
      patrol: "#0f6bff",
      stair_entry: "#f97316",
      stair_switch: "#7c3aed",
      stair_exit: "#0891b2",
      charge: "#15803d",
      transition: "#b45309"
    };
    const radarPlanLabels = {
      measuring: "实测实量",
      modeling: "点云建模",
      both: "实测实量+点云建模",
      none: "不触发"
    };
    const cameraViewers = {
      front: { active: false, hls: null, retryTimer: null, rtcPc: null, rtcFailed: false, whepFailed: false },
      rear: { active: false, hls: null, retryTimer: null, rtcPc: null, rtcFailed: false, whepFailed: false }
    };

    function $(id) { return document.getElementById(id); }
    function text(value) {
      if (value === null || value === undefined || value === "") return "-";
      return String(value).replace(/dddmr/ig, "三维");
    }
    function escapeHtml(value) {
      return text(value)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
    }
    function fmtNumber(value, digits = 2) { return Number.isFinite(value) ? value.toFixed(digits) : "-"; }
    function radarPlanFromSelect(value) {
      if (value === "none") return {enabled: false, scans: []};
      const scans = [];
      if (value === "measuring" || value === "both") {
        scans.push({
          mode: "measuring",
          label: "实测实量",
          result_suffix: "measure",
          artifact_policy: "auto_result",
          manual_measure_required: false
        });
      }
      if (value === "modeling" || value === "both") {
        scans.push({
          mode: "modeling",
          label: "点云建模",
          result_suffix: "cloud",
          artifact_policy: "manual_import",
          manual_measure_required: true
        });
      }
      return {enabled: true, scans};
    }
    function radarPlanText(radar) {
      if (!radar || radar.enabled === false) return "雷达:不触发";
      const scans = Array.isArray(radar.scans) ? radar.scans : [];
      if (!scans.length) return "雷达:实测实量";
      return `雷达:${scans.map(item => item.label || item.mode || "-").join("+")}`;
    }
    function radarPlanSelectValue(radar) {
      if (!radar || radar.enabled === false) return "none";
      const modes = new Set((Array.isArray(radar.scans) ? radar.scans : []).map(item => item && item.mode));
      if (modes.has("measuring") && modes.has("modeling")) return "both";
      if (modes.has("modeling")) return "modeling";
      return "measuring";
    }
    function radarScalarText(value) {
      if (value === null || value === undefined || value === "") return "-";
      if (typeof value === "object") {
        try { return JSON.stringify(value); } catch (_err) { return String(value); }
      }
      return String(value);
    }
    function radarMetricName(metric) {
      const name = metric.measurementItem ?? metric.name ?? metric.label ?? metric.metricName ?? metric.metric;
      if (name !== null && name !== undefined && name !== "") return radarScalarText(name);
      if (metric.path) return radarScalarText(metric.path);
      if (metric.measurementItemId !== null && metric.measurementItemId !== undefined && metric.measurementItemId !== "") {
        return `指标 ${metric.measurementItemId}`;
      }
      return "未命名指标";
    }
    function radarMetricValue(metric) {
      const display = metric.displayValue ?? metric.value ?? metric.rawValue ?? metric.numericValue ?? metric.result;
      const value = radarScalarText(display);
      const unit = radarScalarText(metric.unit ?? metric.measurementUnit ?? "");
      return unit !== "-" && !value.includes(unit) ? `${value} ${unit}` : value;
    }
    function radarMetricVerdict(metric) {
      const explicit = metric.conclusion ?? metric.verdict ?? metric.judgement ?? metric.statusText ?? metric.status;
      if (explicit !== null && explicit !== undefined && explicit !== "") return radarScalarText(explicit);
      const qualified = metric.qualified ?? metric.isQualified ?? metric.pass;
      if (qualified === true || String(qualified).toLowerCase() === "true") return "合格";
      if (qualified === false || String(qualified).toLowerCase() === "false") return "不合格";
      return "-";
    }
    function radarResultMetrics(result) {
      const summary = result && typeof result.summary === "object" ? result.summary : {};
      const automatic = Array.isArray(summary.metrics) ? summary.metrics.filter(item => item && typeof item === "object") : [];
      const manual = result && typeof result.manual_measurement === "object" ? result.manual_measurement : {};
      const manualRows = Array.isArray(manual.measurements)
        ? manual.measurements.filter(item => item && typeof item === "object").map(item => ({...item, source: "人工回填"}))
        : [];
      return automatic.concat(manualRows);
    }
    function radarMetricTableHtml(metrics) {
      if (!metrics.length) return "";
      return `
        <table class="radar-metric-table">
          <thead><tr><th>测量项目</th><th>位置</th><th>结果</th><th>判定</th></tr></thead>
          <tbody>
            ${metrics.map(metric => `
              <tr>
                <td>${escapeHtml(radarMetricName(metric))}</td>
                <td>${escapeHtml(metric.location || metric.source || "-")}</td>
                <td>${escapeHtml(radarMetricValue(metric))}</td>
                <td>${escapeHtml(radarMetricVerdict(metric))}</td>
              </tr>
            `).join("")}
          </tbody>
        </table>`;
    }
    function renderRadarInspection(record) {
      const box = $("radarStatusSummary");
      if (!box) return;
      const parsed = record && (record.parsed || record.raw);
      box.className = "radar-box";
      if (!parsed) {
        box.textContent = "等待数据";
        return;
      }
      if (typeof parsed === "string") {
        box.textContent = parsed;
        return;
      }
      const scanResults = Array.isArray(parsed.scan_results) ? parsed.scan_results : [];
      const displayResult = scanResults.find(item => item && item.summary) || scanResults[0] || {};
      const summary = parsed.summary || displayResult.summary || {};
      const metrics = radarResultMetrics(displayResult.summary ? displayResult : parsed);
      const status = parsed.status || "-";
      const stateText = parsed.state || "-";
      const resultFetchStatus = parsed.result_fetch_status || displayResult.result_fetch_status || "";
      const resultFetchError = parsed.result_fetch_error || displayResult.result_fetch_error || summary.resultFetchError || "";
      const taskId = displayResult.taskId || parsed.taskId || summary.taskId || "-";
      const mode = displayResult.scan_mode || parsed.scan_mode || summary.mode || "-";
      const backend = parsed.backend || "-";
      const started = displayResult.started_at || parsed.started_at || "-";
      const finished = displayResult.finished_at || parsed.finished_at || "-";
      const released = displayResult.scan_released_at || parsed.scan_released_at || "-";
      const durationValue = displayResult.duration_s ?? parsed.duration_s;
      const releaseDurationValue = displayResult.scan_release_duration_s ?? parsed.scan_release_duration_s;
      const duration = Number.isFinite(Number(durationValue)) ? `${Number(durationValue).toFixed(1)}s` : "-";
      const releaseDuration = Number.isFinite(Number(releaseDurationValue)) ? `${Number(releaseDurationValue).toFixed(1)}s` : "-";
      const location = summary.location || {};
      const place = [location.floor, location.room, location.label].filter(Boolean).join(" / ") || "-";
      const statusClass = status === "failed"
        ? "fail"
        : ((stateText === "result_unavailable" || resultFetchStatus === "failed") ? "warn" : radarStatusClass(status || stateText));
      box.textContent = "";
      const head = document.createElement("div");
      head.className = "radar-head";
      const title = document.createElement("span");
      title.className = "radar-title";
      title.textContent = taskId;
      const badge = document.createElement("span");
      badge.className = `check-status ${statusClass}`;
      badge.textContent = `${status} / ${stateText}`;
      head.appendChild(title);
      head.appendChild(badge);
      box.appendChild(head);
      const grid = document.createElement("div");
      grid.className = "radar-grid";
      const rows = [
        ["模式", `${mode} / ${backend}`],
        ["位置", place],
        ["时间", `${started} -> ${finished} / ${duration}`],
        ["可离开", `${released} / ${releaseDuration}`],
        ["指标", `${metrics.length} 项`],
        ["结果", resultFetchStatus === "failed" ? "暂不可用" : (resultFetchStatus || "-")],
        ["摘要", parsed.summary_path || displayResult.summary_path || "-"],
        ["原始", parsed.raw_path || parsed.task_info_path || displayResult.raw_path || displayResult.task_info_path || "-"]
      ];
      for (const [label, value] of rows) {
        const labelEl = document.createElement("div");
        const valueEl = document.createElement("div");
        labelEl.textContent = label;
        valueEl.textContent = value;
        grid.appendChild(labelEl);
        grid.appendChild(valueEl);
      }
      box.appendChild(grid);
      if (metrics.length) {
        const tableWrap = document.createElement("div");
        tableWrap.className = "metric-table";
        tableWrap.innerHTML = radarMetricTableHtml(metrics);
        box.appendChild(tableWrap);
      } else if (resultFetchStatus === "failed" || summary.resultUnavailable) {
        const note = document.createElement("div");
        note.className = "small";
        note.textContent = `结果暂不可用${resultFetchError ? `：${resultFetchError}` : ""}`;
        box.appendChild(note);
      } else if (parsed.error) {
        const note = document.createElement("div");
        note.className = "small";
        note.textContent = parsed.error;
        box.appendChild(note);
      }
    }
    function radarStatusClass(value) {
      const textValue = String(value || "");
      if (["completed", "finished", "downloaded", "imported", "complete"].includes(textValue)) return "ok";
      if (["failed", "error"].includes(textValue)) return "fail";
      return "warn";
    }
    function radarTaskResultsHtml(task) {
      const results = Array.isArray(task.radar_results) ? task.radar_results : [];
      if (!results.length) return "";
      const rows = results.map(item => {
        const waypoint = item.waypoint || {};
        const summary = item.summary || {};
        const metrics = radarResultMetrics(item);
        const artifact = item.manual_artifact || {};
        const manual = item.manual_measurement || {};
        const manualMeasurements = Array.isArray(manual.measurements) ? manual.measurements : [];
        const manualValues = manualMeasurements
          .map(row => `${text(row.name || row.measurementItem || "人工项")}:${text(row.value || row.displayValue || row.rawValue)}`)
          .join("；");
        const title = [
          waypoint.room || waypoint.label || item.waypoint_key || "-",
          waypoint.scan_point || "",
          item.scan_label || item.scan_mode || "-"
        ].filter(Boolean).join(" / ");
        const artifactText = item.scan_mode === "modeling"
          ? `点云:${artifact.artifact_path || item.artifact_status || "待导入"}`
          : "";
        const manualText = item.manual_measure_required
          ? `人工:${manual.status || item.manual_measure_status || "待测量"}`
          : "";
        const manualValueText = manualValues ? `回填:${manualValues}` : "";
        const metricText = metrics.length ? `指标:${metrics.length}项` : "";
        const resultFetchText = item.result_fetch_status === "failed"
          ? `结果暂不可用:${item.result_fetch_error || ""}`
          : (item.error ? `错误:${item.error}` : "");
        const statusText = item.status && item.state && item.state !== item.status
          ? `${item.status} / ${item.state}`
          : (item.status || item.state || "-");
        const statusClass = item.status === "failed"
          ? "fail"
          : ((item.state === "result_unavailable" || item.result_fetch_status === "failed") ? "warn" : radarStatusClass(item.status || item.state));
        const metricRows = metrics.length ? `<div class="metric-table">${radarMetricTableHtml(metrics)}</div>` : "";
        return `
          <div class="radar-result-row">
            <div class="radar-result-head">
              <span>${escapeHtml(title)}</span>
              <span class="check-status ${statusClass}">${escapeHtml(statusText)}</span>
            </div>
            <div class="radar-result-meta">${escapeHtml([item.taskId, item.started_at, item.finished_at].filter(Boolean).join(" / "))}</div>
            <div class="radar-result-meta">${escapeHtml([metricText, artifactText, manualText, manualValueText, resultFetchText].filter(Boolean).join(" / "))}</div>
            <div class="actions">
              ${item.scan_mode === "modeling" ? `<button data-radar-artifact="${escapeHtml(item.run_id)}" data-task-id="${escapeHtml(task.id)}">登记点云</button>` : ""}
              ${item.manual_measure_required ? `<button data-radar-manual="${escapeHtml(item.run_id)}" data-task-id="${escapeHtml(task.id)}">人工回填</button>` : ""}
            </div>
            ${metricRows}
          </div>
        `;
      }).join("");
      return `<div class="radar-results">${rows}</div>`;
    }
    function radarResultLocation(item) {
      const waypoint = item.waypoint && typeof item.waypoint === "object" ? item.waypoint : {};
      const summary = item.summary && typeof item.summary === "object" ? item.summary : {};
      const location = summary.location && typeof summary.location === "object" ? summary.location : {};
      return [
        waypoint.floor || location.floor,
        waypoint.room || waypoint.house || location.room,
        waypoint.scan_point || location.scanPoint,
        waypoint.label || location.label
      ].filter(Boolean).join(" / ") || "未标注位置";
    }
    function renderRadarResultWorkspace() {
      const box = $("radarResultList");
      if (!box) return;
      box.innerHTML = "";
      if ($("radarResultCount")) $("radarResultCount").textContent = String(state.radarResultTotal);
      renderCollectionPager("radarResultPager", state.radarResultPage, state.radarResultTotal, page => {
        state.radarResultPage = page;
        loadRadarResults().catch(console.warn);
      });
      if (!state.radarResults.length) {
        box.innerHTML = '<div class="small">没有匹配的雷达测量结果</div>';
        return;
      }
      for (const item of state.radarResults) {
        const metrics = radarResultMetrics(item);
        const statusText = item.status && item.state && item.status !== item.state
          ? `${item.status} / ${item.state}`
          : (item.status || item.state || "-");
        const statusClass = item.status === "failed"
          ? "fail"
          : ((item.state === "result_unavailable" || item.result_fetch_status === "failed")
            ? "warn"
            : radarStatusClass(item.status || item.state));
        const mode = item.scan_mode || (item.summary || {}).mode || "-";
        const taskId = item.task_id || "";
        const deviceTaskId = item.taskId || "";
        const artifact = item.manual_artifact || {};
        const artifactText = mode === "modeling"
          ? `点云产物：${artifact.artifact_path || item.artifact_status || "待登记"}`
          : "";
        const unavailableText = item.result_fetch_status === "failed" || item.state === "result_unavailable"
          ? `结果暂不可用：${item.result_fetch_error || item.error || "设备结果接口未返回"}`
          : "";
        const emptyText = !metrics.length && !unavailableText
          ? (mode === "modeling" ? artifactText : "该次结果没有结构化指标，可查看原始 JSON")
          : "";
        const row = document.createElement("div");
        row.className = "radar-result-row";
        row.innerHTML = `
          <div class="radar-result-head">
            <span>${escapeHtml(radarResultLocation(item))}</span>
            <span class="check-status ${statusClass}">${escapeHtml(statusText)}</span>
          </div>
          <div class="radar-result-meta">${escapeHtml([
            radarPlanLabels[mode] || item.scan_label || mode,
            `${metrics.length} 项指标`,
            item.finished_at || item.started_at || ""
          ].filter(Boolean).join(" / "))}</div>
          <div class="radar-result-meta">${escapeHtml([taskId ? `任务 ${taskId}` : "", deviceTaskId ? `设备 ${deviceTaskId}` : "", artifactText].filter(Boolean).join(" / "))}</div>
          ${metrics.length ? `<div class="metric-table">${radarMetricTableHtml(metrics)}</div>` : ""}
          ${unavailableText || emptyText ? `<div class="radar-result-notice">${escapeHtml(unavailableText || emptyText)}</div>` : ""}
          <div class="actions radar-result-actions">
            <button type="button" data-radar-open-json="${escapeHtml(item.run_id || "")}" ${item.run_id ? "" : "disabled"}>查看 JSON</button>
            ${taskId ? `<button type="button" data-radar-task-json="${escapeHtml(taskId)}">任务 JSON</button>` : ""}
            ${taskId ? `<button type="button" data-radar-task-csv="${escapeHtml(taskId)}">任务 CSV</button>` : ""}
            ${mode === "modeling" && taskId && item.run_id ? `<button type="button" data-radar-result-artifact="${escapeHtml(item.run_id)}" data-task-id="${escapeHtml(taskId)}">登记点云</button>` : ""}
            ${item.manual_measure_required && taskId && item.run_id ? `<button type="button" data-radar-result-manual="${escapeHtml(item.run_id)}" data-task-id="${escapeHtml(taskId)}">人工回填</button>` : ""}
          </div>`;
        box.appendChild(row);
      }
      for (const button of box.querySelectorAll("[data-radar-open-json]")) {
        button.addEventListener("click", () => window.open(`/api/radar/result?run_id=${encodeURIComponent(button.dataset.radarOpenJson)}`, "_blank"));
      }
      for (const button of box.querySelectorAll("[data-radar-task-json]")) {
        button.addEventListener("click", () => window.open(`/api/radar/task_export?task_id=${encodeURIComponent(button.dataset.radarTaskJson)}&format=json`, "_blank"));
      }
      for (const button of box.querySelectorAll("[data-radar-task-csv]")) {
        button.addEventListener("click", () => window.open(`/api/radar/task_export?task_id=${encodeURIComponent(button.dataset.radarTaskCsv)}&format=csv`, "_blank"));
      }
      for (const button of box.querySelectorAll("[data-radar-result-artifact]")) {
        button.addEventListener("click", async () => {
          await recordRadarArtifact(button.dataset.taskId, button.dataset.radarResultArtifact);
          await loadRadarResults();
        });
      }
      for (const button of box.querySelectorAll("[data-radar-result-manual]")) {
        button.addEventListener("click", async () => {
          await saveRadarManualMeasurement(button.dataset.taskId, button.dataset.radarResultManual);
          await loadRadarResults();
        });
      }
    }
    async function loadRadarResults() {
      if (!$("radarResultList") || state.loadingRadarResults) return;
      state.loadingRadarResults = true;
      try {
        const query = new URLSearchParams({
          offset: String(state.radarResultPage * collectionPageSize),
          limit: String(collectionPageSize)
        });
        if (state.radarResultQuery.trim()) query.set("q", state.radarResultQuery.trim());
        if (state.radarResultMode) query.set("mode", state.radarResultMode);
        let payload = await fetchJson(`/api/radar/results?${query.toString()}`);
        state.radarResults = Array.isArray(payload.results) ? payload.results : [];
        state.radarResultTotal = Number(payload.total || 0);
        state.lastRadarResultsRefreshAt = Date.now();
        const pageCount = Math.max(1, Math.ceil(state.radarResultTotal / collectionPageSize));
        if (state.radarResultPage >= pageCount) {
          state.radarResultPage = pageCount - 1;
          if (state.radarResultTotal) {
            query.set("offset", String(state.radarResultPage * collectionPageSize));
            payload = await fetchJson(`/api/radar/results?${query.toString()}`);
            state.radarResults = Array.isArray(payload.results) ? payload.results : [];
          }
        }
        renderRadarResultWorkspace();
      } catch (err) {
        const box = $("radarResultList");
        if (box) box.innerHTML = `<div class="radar-result-notice fail">${escapeHtml(err.message || err)}</div>`;
      } finally {
        state.loadingRadarResults = false;
      }
    }
    async function loadRadarStatus() {
      try {
        const payload = await fetchJson("/api/radar/status");
        renderRadarInspection(payload.latest || null);
        return payload;
      } catch (err) {
        renderRadarInspection({parsed: {status: "error", state: "error", error: err.message || "无法读取雷达状态"}});
        return null;
      }
    }
    async function startManualRadarScan() {
      const button = $("radarManualScanBtn");
      if (!button) return;
      const oldText = button.textContent;
      button.disabled = true;
      button.textContent = "启动中...";
      try {
        const payload = await api("POST", "/api/radar/manual_start", {mode: $("radarManualMode").value});
        showOperationFeedback("雷达扫描已启动", payload.message || "已按当前位姿启动手动雷达扫描");
        await loadRadarStatus();
      } catch (err) {
        showOperationFeedback("雷达扫描启动失败", err, true);
      } finally {
        button.disabled = false;
        button.textContent = oldText;
      }
    }
    async function recordRadarArtifact(taskId, runId) {
      const artifactPath = window.prompt("请输入已导入/已拷贝的点云工程包路径", "");
      if (artifactPath === null) return;
      const trimmed = artifactPath.trim();
      if (!trimmed) return;
      const note = window.prompt("备注，可留空", "") || "";
      const payload = await api("POST", "/api/radar/artifact", {
        task_id: taskId,
        run_id: runId,
        artifact_path: trimmed,
        note
      });
      setLog("activeTask", payload);
      await loadTasks();
    }
    async function saveRadarManualMeasurement(taskId, runId) {
      const name = window.prompt("测量项名称，例如 开关高度", "");
      if (name === null) return;
      const value = window.prompt("测量值，例如 1.32m", "");
      if (value === null) return;
      const note = window.prompt("备注，可留空", "") || "";
      const payload = await api("POST", "/api/radar/manual_measurement", {
        task_id: taskId,
        run_id: runId,
        measurements: [{name: name.trim(), value: value.trim(), note}],
        note
      });
      setLog("activeTask", payload);
      await loadTasks();
    }
    async function startRemoteStreamPlayback(cameraName) {
      const viewer = cameraViewers[cameraName];
      try {
        await api("POST", "/api/remote_stream", {action: "start", camera: cameraName});
      } catch (err) {
        // The push unit may already be running; keep trying the handshake.
      }
      for (let attempt = 0; attempt < 4; attempt += 1) {
        if (!viewer || !viewer.active) return false;
        const started = await attemptRemoteStreamPlayback(cameraName);
        if (!viewer.active) return false;
        if (started) return true;
        await new Promise(resolve => setTimeout(resolve, 2000));
      }
      return false;
    }
    async function attemptRemoteStreamPlayback(cameraName) {
      const viewer = cameraViewers[cameraName];
      const video = $(`${cameraName}Video`);
      if (!viewer || !video) return false;
      const pc = new RTCPeerConnection({iceServers: []});
      viewer.rtcPc = pc;
      try {
        pc.addTransceiver("video", {direction: "recvonly"});
        pc.addTransceiver("audio", {direction: "recvonly"});
        const trackArrived = new Promise((resolve, reject) => {
          const timer = setTimeout(() => reject(new Error("rtc_timeout")), 5000);
          pc.ontrack = event => {
            clearTimeout(timer);
            if (event.streams && event.streams[0]) {
              video.srcObject = event.streams[0];
            } else {
              video.srcObject = new MediaStream([event.track]);
            }
            resolve();
          };
          pc.oniceconnectionstatechange = () => {
            if (pc.iceConnectionState === "failed" || pc.iceConnectionState === "closed") {
              clearTimeout(timer);
              reject(new Error("ice_failed"));
            }
          };
        });
        const offer = await pc.createOffer();
        await pc.setLocalDescription(offer);
        const signal = await api("POST", "/api/remote_stream", {
          action: "signal",
          camera: cameraName,
          sdp: offer.sdp
        });
        if (!signal || !signal.sdp) throw new Error("signal_failed");
        await pc.setRemoteDescription({type: "answer", sdp: signal.sdp});
        await trackArrived;
        await video.play().catch(() => {});
        pc.onconnectionstatechange = () => {
          if (!viewer.active || viewer.rtcPc !== pc) return;
          if (pc.connectionState === "failed" || pc.connectionState === "disconnected") {
            stopVideoViewer(cameraName);
            // Retry the WebRTC session; startVideoViewer surfaces an error
            // when every attempt fails (no HLS fallback anymore).
            viewer.active = true;
            viewer.rtcFailed = false;
            startVideoViewer(cameraName);
          }
        };
        watchRemoteStreamStall(cameraName, pc, video);
        return viewer.active;
      } catch (err) {
        closeRemoteStreamPeer(cameraName, pc);
        return false;
      }
    }
    function closeRemoteStreamPeer(cameraName, pc) {
      const viewer = cameraViewers[cameraName];
      if (viewer && viewer.rtcPc === pc) viewer.rtcPc = null;
      try {
        pc.ontrack = null;
        pc.oniceconnectionstatechange = null;
        pc.onconnectionstatechange = null;
        pc.close();
      } catch (err) {}
    }
    function showRemoteStreamError(cameraName) {
      const video = $(`${cameraName}Video`);
      if (!video || !video.parentElement) return;
      clearRemoteStreamError(cameraName);
      const overlay = document.createElement("div");
      overlay.id = `${cameraName}StreamError`;
      overlay.style.cssText = "position:absolute;inset:0;z-index:5;display:flex;flex-direction:column;gap:10px;align-items:center;justify-content:center;padding:12px;text-align:center;font-size:14px;color:#e6edf3;background:rgba(11,17,23,0.92);";
      const msg = document.createElement("div");
      msg.textContent = "远程视频连接失败：当前网络可能禁用了 UDP，或机器狗推流异常，请稍后重试。";
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "mini-btn";
      btn.textContent = "重试";
      btn.addEventListener("click", () => {
        const viewer = cameraViewers[cameraName];
        if (!viewer || !viewer.active) return;
        viewer.rtcFailed = false;
        startVideoViewer(cameraName);
      });
      overlay.appendChild(msg);
      overlay.appendChild(btn);
      video.parentElement.appendChild(overlay);
    }
    function clearRemoteStreamError(cameraName) {
      const old = document.getElementById(`${cameraName}StreamError`);
      if (old) old.remove();
    }
    function watchRemoteStreamStall(cameraName, pc, video) {
      let lastTime = -1;
      let stallCount = 0;
      const iv = setInterval(() => {
        const viewer = cameraViewers[cameraName];
        if (!viewer || !viewer.active || viewer.rtcPc !== pc) {
          clearInterval(iv);
          return;
        }
        if (video.readyState < 2 || video.paused) return;
        if (video.currentTime === lastTime) {
          stallCount += 1;
        } else {
          stallCount = 0;
        }
        lastTime = video.currentTime;
        if (stallCount >= 2) {
          clearInterval(iv);
          closeRemoteStreamPeer(cameraName, pc);
          const v = cameraViewers[cameraName];
          if (v && v.active) {
            // Full WebRTC retry cycle; startVideoViewer shows an error when
            // every attempt fails (no HLS fallback anymore).
            v.rtcFailed = false;
            startVideoViewer(cameraName);
          }
        }
      }, 4000);
    }
    function stopRemoteStreamPush(cameraName) {
      api("POST", "/api/remote_stream", {action: "stop", camera: cameraName}).catch(() => {});
    }
    async function startLocalWhepPlayback(cameraName) {
      // Local operators get sub-second latency via MediaMTX WHEP (WebRTC);
      // LL-HLS below is only the fallback when the handshake fails.
      const viewer = cameraViewers[cameraName];
      const video = $(`${cameraName}Video`);
      if (!viewer || !video) return false;
      const pathName = cameraName === "front" ? "video1" : "video2";
      const whepUrl = `${window.location.protocol}//${window.location.hostname}:8889/${pathName}/whep`;
      const pc = new RTCPeerConnection({iceServers: []});
      viewer.rtcPc = pc;
      try {
        pc.addTransceiver("video", {direction: "recvonly"});
        const trackArrived = new Promise((resolve, reject) => {
          const timer = setTimeout(() => reject(new Error("whep_timeout")), 12000);
          pc.ontrack = event => {
            clearTimeout(timer);
            if (event.streams && event.streams[0]) {
              video.srcObject = event.streams[0];
            } else {
              video.srcObject = new MediaStream([event.track]);
            }
            resolve();
          };
          pc.oniceconnectionstatechange = () => {
            if (pc.iceConnectionState === "failed" || pc.iceConnectionState === "closed") {
              clearTimeout(timer);
              reject(new Error("ice_failed"));
            }
          };
        });
        const offer = await pc.createOffer();
        await pc.setLocalDescription(offer);
        await new Promise(resolve => {
          if (pc.iceGatheringState === "complete") return resolve();
          const timer = setTimeout(resolve, 1500);
          pc.onicegatheringstatechange = () => {
            if (pc.iceGatheringState === "complete") {
              clearTimeout(timer);
              resolve();
            }
          };
        });
        const resp = await fetch(whepUrl, {
          method: "POST",
          headers: {"Content-Type": "application/sdp"},
          body: pc.localDescription.sdp
        });
        if (!resp.ok) throw new Error("whep_http_" + resp.status);
        const answerSdp = await resp.text();
        await pc.setRemoteDescription({type: "answer", sdp: answerSdp});
        await trackArrived;
        await video.play().catch(() => {});
        pc.onconnectionstatechange = () => {
          if (!viewer.active || viewer.rtcPc !== pc) return;
          if (pc.connectionState === "failed" || pc.connectionState === "disconnected") {
            closeRemoteStreamPeer(cameraName, pc);
            viewer.whepFailed = true;
            startVideoViewer(cameraName);
          }
        };
        return viewer.active;
      } catch (err) {
        closeRemoteStreamPeer(cameraName, pc);
        return false;
      }
    }
    function stopVideoViewer(cameraName) {
      const viewer = cameraViewers[cameraName];
      const video = $(`${cameraName}Video`);
      if (!viewer || !video) return;
      clearRemoteStreamError(cameraName);
      viewer.active = false;
      if (viewer.retryTimer !== null) {
        clearTimeout(viewer.retryTimer);
        viewer.retryTimer = null;
      }
      if (viewer.hls) {
        viewer.hls.destroy();
        viewer.hls = null;
      }
      if (viewer.rtcPc) {
        closeRemoteStreamPeer(cameraName, viewer.rtcPc);
      }
      video.srcObject = null;
      video.pause();
      video.removeAttribute("src");
      video.load();
      if (remoteStreamEnabled) {
        stopRemoteStreamPush(cameraName);
      }
    }
    async function startVideoViewer(cameraName) {
      const viewer = cameraViewers[cameraName];
      const video = $(`${cameraName}Video`);
      if (!viewer || !video || !viewer.active) return;
      clearRemoteStreamError(cameraName);
      if (remoteStreamEnabled) {
        // Public path: WebRTC over UDP only. The LL-HLS fallback was removed;
        // if the handshake keeps failing, surface an error instead.
        if (!viewer.rtcFailed && typeof RTCPeerConnection === "function") {
          const rtcStarted = await startRemoteStreamPlayback(cameraName);
          if (!viewer.active) return;
          if (rtcStarted) return;
        }
        viewer.rtcFailed = true;
        showRemoteStreamError(cameraName);
        return;
      }
      if (!viewer.whepFailed && typeof RTCPeerConnection === "function") {
        const whepStarted = await startLocalWhepPlayback(cameraName);
        if (!viewer.active) return;
        if (whepStarted) return;
      }
      viewer.whepFailed = true;
      const source = video.dataset.src;
      if (!window.Hls && !video.canPlayType("application/vnd.apple.mpegurl")) {
        const HlsLibrary = await ensureHlsLibrary();
        if (!viewer.active) return;
        if (!HlsLibrary) {
          viewer.retryTimer = setTimeout(() => {
            viewer.retryTimer = null;
            startVideoViewer(cameraName);
          }, 1500);
          return;
        }
      }
      const HlsCtor = window.Hls;
      if (HlsCtor && HlsCtor.isSupported()) {
        const hls = new HlsCtor({
          lowLatencyMode: true,
          // Keep the player close to the LL-HLS edge; the gateway publishes
          // roughly 0.6 s segments and a 0.5 s part hold-back.
          liveSyncDuration: 0.75,
          // Keep the low-latency target, but allow a slower mobile path to
          // catch up instead of jumping past still-in-flight segments.
          liveMaxLatencyDuration: 8,
          maxLiveSyncPlaybackRate: 1.8,
          maxBufferLength: 4,
          maxMaxBufferLength: 10,
          highBufferWatchdogPeriod: 1,
          maxBufferHole: 0.3,
          backBufferLength: 0,
          startFragPrefetch: true,
          manifestLoadingMaxRetry: 6,
          manifestLoadingRetryDelay: 1000,
          manifestLoadingMaxRetryTimeout: 8000,
          levelLoadingMaxRetry: 6,
          levelLoadingRetryDelay: 1000,
          levelLoadingMaxRetryTimeout: 8000,
          fragLoadingMaxRetry: 8,
          fragLoadingRetryDelay: 1000,
          fragLoadingMaxRetryTimeout: 10000
        });
        viewer.hls = hls;
        hls.on(HlsCtor.Events.MEDIA_ATTACHED, () => hls.loadSource(source));
        hls.on(HlsCtor.Events.MANIFEST_PARSED, () => video.play().catch(() => {}));
        hls.on(HlsCtor.Events.LEVEL_UPDATED, () => {
          if (!viewer.active || viewer.hls !== hls || video.readyState < 2) return;
          const livePosition = Number(hls.liveSyncPosition);
          const latency = Number(hls.latency);
          if (!Number.isFinite(livePosition) || !Number.isFinite(latency)) return;
          // A slow public path can accumulate stale buffered media. Jump once
          // to the current live point, then let Hls.js resume normal playback.
          if (latency > 8 && Math.abs(video.currentTime - livePosition) > 0.75) {
            video.currentTime = livePosition;
          }
        });
        hls.on(HlsCtor.Events.ERROR, (_event, data) => {
          if (!viewer.active || viewer.hls !== hls) return;
          if (data.type === HlsCtor.ErrorTypes.MEDIA_ERROR) {
            hls.recoverMediaError();
            return;
          }
          if (!data.fatal) return;
          hls.destroy();
          if (viewer.hls === hls) viewer.hls = null;
          viewer.retryTimer = setTimeout(() => {
            viewer.retryTimer = null;
            startVideoViewer(cameraName);
          }, 1500);
        });
        hls.attachMedia(video);
        return;
      }
      if (video.canPlayType("application/vnd.apple.mpegurl")) {
        video.src = source;
        video.play().catch(() => {});
      }
    }
    function setVideoActive(cameraName) {
      const frontWasActive = cameraViewers.front.active;
      for (const name of ["front", "rear"]) {
        const viewer = cameraViewers[name];
        const btn = $(`${name}VideoBtn`);
        if (!viewer || !btn) continue;
        stopVideoViewer(name);
        if (name === cameraName) {
          viewer.active = true;
          viewer.whepFailed = false;
          startVideoViewer(name);
          btn.textContent = "关闭";
          btn.classList.add("active");
        } else {
          btn.textContent = "打开";
          btn.classList.remove("active");
        }
      }
      if (frontWasActive && !cameraViewers.front.active) {
        const toggle = $("yoloEnabledToggle");
        if (toggle && toggle.checked && !state.yoloControlBusy) {
          toggle.checked = false;
          setYoloEnabled(false);
        }
      }
      renderYoloWorkspace(state.latest || {});
    }
    function toggleVideo(cameraName) {
      const viewer = cameraViewers[cameraName];
      setVideoActive(viewer && viewer.active ? null : cameraName);
    }
	    function fmtPose(pose, yawScale = 1.0) {
      if (!pose || !Number.isFinite(Number(pose.x)) || !Number.isFinite(Number(pose.y))) return "-";
      const yaw = Number(pose.display_yaw !== undefined ? pose.display_yaw : pose.yaw);
      const yawText = Number.isFinite(yaw) ? ` / ${fmtNumber(yaw * yawScale, yawScale === 1.0 ? 2 : 0)}${yawScale === 1.0 ? "rad" : "°"}` : "";
      return `x ${fmtNumber(Number(pose.x), 2)} / y ${fmtNumber(Number(pose.y), 2)}${yawText}`;
    }
    function planarError(a, b) {
      if (!a || !b) return null;
      const ax = Number(a.x);
      const ay = Number(a.y);
      const bx = Number(b.x);
      const by = Number(b.y);
      if (!Number.isFinite(ax) || !Number.isFinite(ay) || !Number.isFinite(bx) || !Number.isFinite(by)) return null;
      return Math.hypot(ax - bx, ay - by);
    }
    function navFeedbackPose(feedback) {
      if (!feedback) return null;
      return {
        x: feedback.pose_x,
        y: feedback.pose_y,
        yaw: feedback.pose_yaw
      };
    }
    function latestNavFeedbackPose(payload = state.latest) {
      if (!payload) return null;
      const active = payload.active_task || null;
      const waypoint = payload.active_waypoint && payload.active_waypoint.parsed ? payload.active_waypoint.parsed : null;
      const feedback = (waypoint && waypoint.nav_feedback) || (active && active.last_nav_feedback) || null;
      const pose = navFeedbackPose(feedback);
      if (!pose || !Number.isFinite(Number(pose.x)) || !Number.isFinite(Number(pose.y))) return null;
      let age = waypoint && waypoint.nav_feedback_age_s;
      if ((age === null || age === undefined) && active && active.last_nav_feedback_at) age = null;
      return {
        x: Number(pose.x),
        y: Number(pose.y),
        yaw: Number.isFinite(Number(pose.yaw)) ? Number(pose.yaw) : 0,
        age_s: Number.isFinite(Number(age)) ? Number(age) : null
      };
    }
    function poseUnavailableText(payload = state.latest) {
      if (!payload) return "等待状态";
      const poseAge = poseAgeSec(payload);
      if (payload.localization_ok === false) {
        if (payload.pose && hasFreshPose(payload)) {
          return "地图位姿仍在刷新，但定位状态未确认";
        }
        return "未定位，重定位后显示地图位姿";
      }
      if (payload.localization_ok === true && payload.pose && !hasFreshPose(payload)) {
        const ageText = poseAge === null || poseAge === undefined ? "" : `，最后 ${fmtAge(poseAge)}前`;
        return `地图位姿过期${ageText}`;
      }
      if (payload.localization_ok === true && !payload.pose) {
        return localizationOwner() === "official_mcl"
          ? "定位已确认，但还未收到 MCL 地图位姿（/m20pro/dddmr/map_pose）"
          : "定位已确认，但还未收到 /m20pro_tcp_bridge/map_pose";
      }
      const odom = payload.odom && payload.odom.pose ? payload.odom.pose : null;
      if (odom && Number.isFinite(Number(odom.x)) && Math.abs(Number(odom.x)) > 100) {
        return "仅收到 /ODOM，坐标未对齐当前地图";
      }
      return "等待地图位姿";
    }
    function localizationOwner() {
      const ownerStatus = state.latest && state.latest.localization_status;
      return ownerStatus && ownerStatus.localization_owner ? String(ownerStatus.localization_owner) : "factory";
    }
    function renderLocalizationStatus(payload = state.latest) {
      const box = $("localizationStatus");
      if (!box) return;
      const rawStatus = payload && payload.localization_status ? payload.localization_status : null;
      box.className = "preflight-summary";
      if (!rawStatus) {
        box.classList.add("warn");
        box.textContent = "等待定位状态";
        return;
      }
      const status = {...rawStatus};
      const relocalization = payload && payload.relocalization_result ? payload.relocalization_result : null;
      if (String(status.localization_owner || "factory") !== "official_mcl" && !status.tcp_2101_result && relocalization && relocalization.raw) {
        const raw = String(relocalization.raw || "");
        status.tcp_2101_result = raw;
        status.tcp_2101_accepted = raw.startsWith("success");
        status.tcp_2101_failed = raw.startsWith("failed:");
        if (Number.isFinite(Number(payload && payload.node_time)) && Number.isFinite(Number(relocalization.last_update))) {
          status.tcp_2101_age_sec = Math.max(0, Number(payload.node_time) - Number(relocalization.last_update));
          status.tcp_2101_recent = status.tcp_2101_age_sec <= 300;
        }
      }
      if (status.factory_localization_ok === undefined && payload && payload.factory_localization_ok !== undefined) {
        status.factory_localization_ok = payload.factory_localization_ok;
      }
      if (status.pose_fresh === undefined && payload && payload.pose_fresh !== undefined) {
        status.pose_fresh = payload.pose_fresh;
      }
      const confirmed = status.confirmed === true;
      const mapLock = !!status.map_relocalization_required;
      const finalSuccess = confirmed && !mapLock;
      const runningPoseMismatch = finalSuccess && status.pose_near_2101 === false;
      box.classList.add(finalSuccess ? "ok" : "fail");
      box.innerHTML = "";
      const verdict = document.createElement("div");
      verdict.className = "localization-verdict";
      verdict.textContent = finalSuccess ? "最终结论：重定位成功" : "最终结论：重定位失败";
      box.appendChild(verdict);
      const message = document.createElement("div");
      message.className = "localization-message";
      message.textContent = finalSuccess ? (status.message || "定位已确认") : (status.message || status.code || "定位未确认");
      box.appendChild(message);
      const poseAge = Number.isFinite(Number(status.pose_age_sec)) ? fmtAge(Number(status.pose_age_sec)) : "-";
      const poseError = Number.isFinite(Number(status.pose_error_m)) ? Number(status.pose_error_m) : null;
      const tcpAge = Number.isFinite(Number(status.tcp_2101_age_sec)) ? fmtAge(Number(status.tcp_2101_age_sec)) : null;
      const tcpResult = String(status.tcp_2101_result || "");
      let tcpText = "无回执";
      let tcpState = "fail";
      if (status.tcp_2101_accepted) {
        tcpText = `${status.tcp_2101_recent === false ? "旧回执" : "已收到回执"}${tcpAge ? " / " + tcpAge + "前" : ""}`;
        tcpState = finalSuccess ? "ok" : "warn";
      } else if (status.tcp_2101_failed) {
        tcpText = `失败回执${tcpAge ? " / " + tcpAge + "前" : ""}`;
      } else if (tcpResult) {
        tcpText = `未通过回执${tcpAge ? " / " + tcpAge + "前" : ""}`;
      }
      const poseDriftText = runningPoseMismatch && poseError !== null ? ` / 已离开重定位点 ${poseError.toFixed(2)}m` : "";
      const factoryOk = status.factory_localization_ok === true || status.localization_ok === true;
      const poseText = status.pose_fresh
        ? `新鲜 / ${poseAge}前${poseDriftText}`
        : (status.pose_ok ? `过期或未确认 / ${poseAge}前` : "缺失或无效");
      const poseState = status.pose_fresh ? "ok" : "warn";
      const mclOwned = String(status.localization_owner || "factory") === "official_mcl";
      let rows;
      if (mclOwned) {
        rows = [
          ["MCL 定位", status.localization_ok === true ? "已确认" : "未确认", status.localization_ok === true ? "ok" : "fail"],
          ["MCL 地图位姿", poseText, poseState],
          ["导航链路", status.navigation_ready === true ? "就绪" : "恢复中", status.navigation_ready === true ? "ok" : "warn"],
          ["固定地图", mapLock ? "仍需重定位" : "已确认", mapLock ? "warn" : "ok"],
        ];
      } else {
        rows = [
          ["定位确认", factoryOk ? "已确认" : "未确认", factoryOk ? "ok" : "fail"],
          ["地图位姿", poseText, poseState],
          ["固定地图", mapLock ? "仍需重定位" : "已确认", mapLock ? "warn" : "ok"],
        ];
        if (!finalSuccess && status.tcp_2101_required !== false) {
          rows.unshift(["2101回执", tcpText, tcpState]);
        }
      }
      const evidence = document.createElement("div");
      evidence.className = "localization-evidence";
      rows.forEach(([label, value, cls]) => {
        const row = document.createElement("div");
        row.className = "localization-row";
        const name = document.createElement("span");
        name.className = "localization-label";
        name.textContent = label;
        const stateText = document.createElement("span");
        stateText.className = `localization-value ${cls}`;
        stateText.textContent = value;
        row.appendChild(name);
        row.appendChild(stateText);
        evidence.appendChild(row);
      });
      box.appendChild(evidence);
    }
    function fmtAge(age) {
      if (age === null || age === undefined) return "-";
      if (age < 1.0) return "<1s";
      return `${age.toFixed(0)}s`;
    }
    function poseAgeSec(payload = state.latest) {
      if (!payload) return null;
      if (payload.pose_age_sec !== null && payload.pose_age_sec !== undefined) return Number(payload.pose_age_sec);
      const pose = payload.pose;
      if (!pose || payload.node_time === null || payload.node_time === undefined || pose.last_update === null || pose.last_update === undefined) return null;
      const age = Number(payload.node_time) - Number(pose.last_update);
      return Number.isFinite(age) ? Math.max(0, age) : null;
    }
    function hasFreshPose(payload = state.latest) {
      if (!payload || !payload.pose) return false;
      if (effectiveCurrentMapId() && !localizationConfirmedForDisplay(payload)) return false;
      if (payload.pose_fresh === true) return true;
      if (payload.pose_fresh === false) return false;
      if (payload.localization_ok !== true) return false;
      const age = poseAgeSec(payload);
      return Number.isFinite(age) && age <= 3.0;
    }
    function freshPose(payload = state.latest) {
      return hasFreshPose(payload) ? payload.pose : null;
    }
    function yawDelta(from, to) {
      return Math.atan2(Math.sin(to - from), Math.cos(to - from));
    }
    function stableRobotDisplayPose(pose, activeTask = null) {
      if (!pose || !Number.isFinite(Number(pose.x)) || !Number.isFinite(Number(pose.y))) {
        state.robotDisplayPose = null;
        return null;
      }
      const raw = {
        x: Number(pose.x),
        y: Number(pose.y),
        yaw: normalizeYaw(Number.isFinite(Number(pose.display_yaw)) ? pose.display_yaw : pose.yaw)
      };
      if (activeTask && activeTask.status === "running") {
        state.robotDisplayPose = raw;
        return raw;
      }
      const prev = state.robotDisplayPose;
      if (!prev) {
        state.robotDisplayPose = raw;
        return raw;
      }
      const dx = raw.x - prev.x;
      const dy = raw.y - prev.y;
      const dist = Math.hypot(dx, dy);
      const dyaw = yawDelta(prev.yaw, raw.yaw);
      if (dist > 0.35 || Math.abs(dyaw) > 0.35) {
        state.robotDisplayPose = raw;
        return raw;
      }
      if (dist < 0.03 && Math.abs(dyaw) < 0.035) return prev;
      const alpha = 0.4;
      state.robotDisplayPose = {
        x: prev.x + dx * alpha,
        y: prev.y + dy * alpha,
        yaw: normalizeYaw(prev.yaw + dyaw * alpha)
      };
      return state.robotDisplayPose;
    }
    function mapRecordById(mapId) {
      const id = String(mapId || "");
      if (!id) return null;
      return state.maps.find(item => String(item.id || "") === id) || null;
    }
    function displayedMapFloor() {
      const record = mapRecordById(state.selectedMapId || state.effectiveMapId);
      if (record && record.floor) return String(record.floor).trim();
      if (state.spatialMap && state.spatialMap.floor) return String(state.spatialMap.floor).trim();
      return state.map && state.map.floor ? String(state.map.floor).trim() : "";
    }
    function currentRobotFloor(payload = state.latest) {
      return payload && payload.floor ? String(payload.floor).trim() : "";
    }
    function mappingDraftFloor(payload = state.latest) {
      const workspaceFloor = state.dddmrMapAssets
        && state.dddmrMapAssets.workspace
        && state.dddmrMapAssets.workspace.current_floor
        ? String(state.dddmrMapAssets.workspace.current_floor).trim()
        : "";
      return displayedMapFloor() || currentRobotFloor(payload) || workspaceFloor;
    }
    function syncMappingDraftControls(floor = mappingDraftFloor()) {
      const mode = $("mappingMode");
      const floorsInput = $("mappingFloors");
      if (mode) mode.value = "single";
      if (floorsInput) floorsInput.value = floor ? String(floor).trim() : "";
    }
    function isViewingRobotFloor(payload = state.latest) {
      if (!state.selectedMapId) return true;
      const shownFloor = displayedMapFloor();
      const robotFloor = currentRobotFloor(payload);
      if (!shownFloor) return true;
      // Before relocalization the factory floor can be unknown. A pending
      // draft is an explicit operator preview on the selected map, so only a
      // confirmed different floor should suppress its red scan overlay.
      if (!robotFloor) return true;
      return shownFloor === robotFloor;
    }
    function selectedMapRelocalizationText(payload = state.latest) {
      const effectiveMapId = effectiveCurrentMapId();
      if (!effectiveMapId || !payload) return "";
      const required = payload.map_relocalization_required
        || (payload.localization_status && payload.localization_status.map_relocalization_required);
      if (!required) return "";
      const record = mapRecordById(effectiveMapId);
      const name = record ? (record.name || record.id) : "当前地图";
      return required.message || `${name} 已切换，重新重定位成功前不显示机器狗实时位姿`;
    }
    function liveRobotLayerBlockedText(payload = state.latest) {
      const relocalization = selectedMapRelocalizationText(payload);
      if (relocalization) return relocalization;
      const mismatch = selectedMapFloorMismatchText(payload);
      if (mismatch) return mismatch;
      if (!hasFreshPose(payload)) return "当前地图位姿未确认";
      return "";
    }
    function canDrawLiveRobotLayer(payload = state.latest) {
      if (!payload) return false;
      return !liveRobotLayerBlockedText(payload);
    }
    function selectedMapFloorMismatchText(payload = state.latest) {
      const shownFloor = displayedMapFloor();
      const robotFloor = currentRobotFloor(payload);
      if (!state.selectedMapId || !shownFloor) return "";
      if (!robotFloor) return `正在查看 ${shownFloor}，尚未收到机器狗真实楼层`;
      if (shownFloor !== robotFloor) return `正在查看 ${shownFloor}，机器狗实际在 ${robotFloor}`;
      return "";
    }
    function localizationConfirmedForDisplay(payload = state.latest) {
      const status = payload && payload.localization_status ? payload.localization_status : null;
      return !!(
        status
        && status.confirmed === true
        && status.pose_fresh !== false
        && !status.map_relocalization_required
      );
    }
    function localizationDraftActive() {
      // The draft remains the active preview until it is confirmed or replaced;
      // it must not depend on which popover/tab currently owns pointer focus.
      return !!state.localizeDraft;
    }
    function markBlockedReason(payload = state.latest) {
      if (!state.spatialMap) return "还没有三维空间地图，等点云地图加载后再标点";
      if (!effectiveCurrentMapId()) return "当前三维空间地图还没有匹配到楼层地图记录，不能保存任务点";
      const selectedMapStatus = (payload && payload.selected_map_status) || state.selectedMapStatus;
      if (selectedMapStatus && selectedMapStatus.ready === false) {
        return selectedMapStatus.message || "当前空间地图与实时导航地图不一致，不能保存任务点";
      }
      const shownFloor = displayedMapFloor();
      const inputFloor = $("markFloor") ? $("markFloor").value.trim() : "";
      if (shownFloor && inputFloor && shownFloor !== inputFloor) {
        return `当前显示 ${shownFloor} 地图，点位楼层填的是 ${inputFloor}；请先确认楼层`;
      }
      return "";
    }
    function updateMarkControls(payload = state.latest) {
      const saveBtn = $("saveMarkBtn");
      const usePoseBtn = $("useRobotPoseBtn");
      const reason = markBlockedReason(payload);
      if (saveBtn) {
        const poseReason = state.markDraft ? "" : "先在空间视图上拖拽箭头确定点位和朝向";
        saveBtn.disabled = !!reason || !!poseReason;
        saveBtn.title = reason || poseReason || "保存当前空间地图上的点位";
      }
      if (usePoseBtn) {
        const mismatch = selectedMapFloorMismatchText(payload);
        const selectedMapStatus = (payload && payload.selected_map_status) || state.selectedMapStatus;
        let poseReason = "";
        if (mismatch) poseReason = `${mismatch}，不能把实时位姿保存到这张地图`;
        else if (selectedMapStatus && selectedMapStatus.ready === false) {
          poseReason = selectedMapStatus.message || "网页选择地图与当前导航地图不一致，请先切换到正确地图并重定位";
        } else if (!payload || !hasFreshPose(payload)) {
          poseReason = "先完成重定位，看到定位页显示重定位成功并收到实时位姿后再取当前位姿";
        }
        const effectiveMapId = effectiveCurrentMapId();
        usePoseBtn.disabled = !!poseReason || !effectiveMapId;
        usePoseBtn.title = poseReason || (effectiveMapId ? "使用当前机器人位姿填入点位" : "等待实时地图匹配固定地图");
      }
    }
    function formatUsageMode(value) {
      if (value === null || value === undefined || value === "") return null;
      const map = {
        0: "常规",
        1: "导航",
        2: "辅助"
      };
      const key = Number(value);
      const label = Number.isFinite(key) && Object.prototype.hasOwnProperty.call(map, key) ? map[key] : String(value);
      return `使用模式 ${label}`;
    }
    function formatOoa(value) {
      if (value === null || value === undefined || value === "") return null;
      const map = {
        0: "未启动",
        1: "空闲中",
        2: "未触发避障",
        3: "主动避障中"
      };
      const key = Number(value);
      const label = Number.isFinite(key) && Object.prototype.hasOwnProperty.call(map, key) ? map[key] : String(value);
      return `辅助避障 ${label}`;
    }
    function payloadMessage(payload, fallback = "操作已完成") {
      if (typeof payload === "string") return payload;
      if (!payload || typeof payload !== "object") return fallback;
      if (payload["最终结论"]) {
        return [payload["最终结论"], payload["判定依据"] || payload["失败原因"], payload["更新时间"]].filter(Boolean).join(" / ");
      }
      return String(payload.message || payload.summary || payload.error || payload.code || fallback);
    }
    function showOperationFeedback(title, payload, failed = false, context = "") {
      const dialog = $("operationFeedbackDialog");
      if (!dialog) return;
      $("operationFeedbackTitle").textContent = title || (failed ? "操作失败" : "操作完成");
      $("operationFeedbackContext").textContent = context;
      const message = $("operationFeedbackMessage");
      message.className = `operation-message${failed ? " fail" : ""}`;
      message.textContent = payloadMessage(payload, failed ? "操作失败" : "操作已完成");
      if (dialog.open) dialog.close();
      dialog.showModal();
    }
    let teleopConfirmResolver = null;
    function closeTeleopConfirm(confirmed) {
      const dialog = $("teleopConfirmDialog");
      if (dialog && dialog.open) dialog.close();
      const resolver = teleopConfirmResolver;
      teleopConfirmResolver = null;
      if (resolver) resolver(Boolean(confirmed));
    }
    function requestTeleopConfirmation(title, message) {
      const dialog = $("teleopConfirmDialog");
      if (!dialog) return Promise.resolve(false);
      if (teleopConfirmResolver) closeTeleopConfirm(false);
      $("teleopConfirmTitle").textContent = title || "确认遥控动作";
      $("teleopConfirmContext").textContent = "确认窗口不会暂停遥控心跳";
      $("teleopConfirmMessage").textContent = message || "确认执行该动作？";
      dialog.showModal();
      return new Promise(resolve => { teleopConfirmResolver = resolve; });
    }
    function setLog(id, payload) {
      const box = $(id);
      if (box) box.textContent = payloadMessage(payload, "等待状态更新");
      if (id === "activeTask" && payload && payload.ok === false) showOperationFeedback("任务操作", payload, true);
      if (id === "mapsLog" && payload && payload.ok === false) showOperationFeedback("地图操作", payload, true);
    }
    const statusPopoverIds = {
      battery: "batteryStatusPopover",
      map: "mapStatusPopover",
      localization: "localizationStatusPopover",
      preflight: "preflightStatusPopover",
      radar: "radarStatusPopover",
      recording: "recordingStatusPopover",
      task: "taskStatusPopover",
      teleop: "teleopStatusPopover"
    };
    const statusButtonIds = {
      battery: "batteryStatusBtn",
      map: "mapStatusBtn",
      localization: "localizationStatusBtn",
      preflight: "preflightStatusBtn",
      radar: "radarStatusBtn",
      recording: "recordingStatusBtn",
      task: "taskStatusBtn",
      teleop: "teleopStatusBtn"
    };
    const teleopPopoverStorageKey = "m20proTeleopPopoverPos";
    function loadTeleopPopoverPos() {
      try {
        const parsed = JSON.parse(window.localStorage.getItem(teleopPopoverStorageKey) || "null");
        if (parsed && Number.isFinite(Number(parsed.left)) && Number.isFinite(Number(parsed.top))) {
          return {left: Number(parsed.left), top: Number(parsed.top)};
        }
      } catch (err) {
        console.warn(err);
      }
      return null;
    }
    function saveTeleopPopoverPos(pos) {
      try {
        window.localStorage.setItem(teleopPopoverStorageKey, JSON.stringify({left: Math.round(pos.left), top: Math.round(pos.top)}));
      } catch (err) {
        console.warn(err);
      }
    }
    function clampTeleopPopoverPos(pos, popover) {
      const viewportPadding = 12;
      const width = popover.offsetWidth || 296;
      const height = popover.offsetHeight || 200;
      return {
        left: Math.max(viewportPadding, Math.min(pos.left, Math.max(viewportPadding, window.innerWidth - viewportPadding - width))),
        top: Math.max(viewportPadding, Math.min(pos.top, Math.max(viewportPadding, window.innerHeight - viewportPadding - height)))
      };
    }
    function positionTeleopPopover(popover) {
      const viewportPadding = 12;
      const saved = loadTeleopPopoverPos();
      // Default: bottom-left corner keeps the right camera column visible.
      const pos = saved || {
        left: viewportPadding,
        top: window.innerHeight - viewportPadding - (popover.offsetHeight || 200)
      };
      const clamped = clampTeleopPopoverPos(pos, popover);
      popover.style.left = `${Math.round(clamped.left)}px`;
      popover.style.top = `${Math.round(clamped.top)}px`;
      popover.style.maxHeight = `${Math.max(120, Math.round(window.innerHeight - clamped.top - viewportPadding))}px`;
    }
    function initTeleopPopoverDrag(popover) {
      const head = popover.querySelector(".status-popover-head");
      if (!head || head.dataset.teleopDragBound === "true") return;
      head.dataset.teleopDragBound = "true";
      head.style.touchAction = "none";
      head.addEventListener("pointerdown", event => {
        if (event.target.closest("button")) return;
        event.preventDefault();
        const rect = popover.getBoundingClientRect();
        const offsetX = event.clientX - rect.left;
        const offsetY = event.clientY - rect.top;
        head.setPointerCapture(event.pointerId);
        const move = moveEvent => {
          const next = clampTeleopPopoverPos({left: moveEvent.clientX - offsetX, top: moveEvent.clientY - offsetY}, popover);
          popover.style.left = `${Math.round(next.left)}px`;
          popover.style.top = `${Math.round(next.top)}px`;
        };
        const finish = upEvent => {
          head.removeEventListener("pointermove", move);
          head.removeEventListener("pointerup", finish);
          head.removeEventListener("pointercancel", finish);
          if (head.hasPointerCapture(upEvent.pointerId)) head.releasePointerCapture(upEvent.pointerId);
          const rectNow = popover.getBoundingClientRect();
          saveTeleopPopoverPos({left: rectNow.left, top: rectNow.top});
        };
        head.addEventListener("pointermove", move);
        head.addEventListener("pointerup", finish);
        head.addEventListener("pointercancel", finish);
      });
    }
    function positionStatusPopover(name) {
      const popover = $(statusPopoverIds[name]);
      const button = $(statusButtonIds[name]);
      if (!popover || !button || popover.hidden) return;
      if (name === "teleop") {
        initTeleopPopoverDrag(popover);
        positionTeleopPopover(popover);
        return;
      }
      const buttonRect = button.getBoundingClientRect();
      const viewportPadding = 12;
      const gap = 8;
      const popoverWidth = popover.offsetWidth;
      const popoverHeight = popover.offsetHeight;
      let left = buttonRect.left;
      let top = buttonRect.bottom + gap;
      if (left + popoverWidth > window.innerWidth - viewportPadding) {
        left = window.innerWidth - viewportPadding - popoverWidth;
      }
      left = Math.max(viewportPadding, left);
      const bottomSpace = window.innerHeight - top - viewportPadding;
      if (popoverHeight > bottomSpace && buttonRect.top - gap - viewportPadding >= popoverHeight) {
        top = buttonRect.top - gap - popoverHeight;
      }
      top = Math.max(viewportPadding, top);
      const availableHeight = Math.max(120, window.innerHeight - top - viewportPadding);
      popover.style.left = `${Math.round(left)}px`;
      popover.style.top = `${Math.round(top)}px`;
      popover.style.maxHeight = `${Math.round(availableHeight)}px`;
    }
    function positionOpenStatusPopover() {
      for (const name of Object.keys(statusPopoverIds)) {
        const popover = $(statusPopoverIds[name]);
        if (popover && !popover.hidden) positionStatusPopover(name);
      }
    }
    function setStatusPopover(name, open) {
      if (state.teleop.sessionId && (name !== "teleop" || !open)) return;
      for (const [key, id] of Object.entries(statusPopoverIds)) {
        const popover = $(id);
        const button = $(statusButtonIds[key]);
        if (!popover || !button) continue;
        const visible = key === name && open;
        popover.hidden = !visible;
        button.setAttribute("aria-expanded", visible ? "true" : "false");
        if (visible) positionStatusPopover(key);
      }
      state.localizationPopoverOpen = name === "localization" && open;
      if (state.localizationPopoverOpen) {
        state.view.panMode = false;
        $("panModeBtn").classList.remove("active-tool");
        $("cursor").textContent = "重定位取点：在地图上拖拽设置位置和朝向";
      }
      if (name === "map" && open) {
        renderDddmrMapAssets(state.dddmrMapAssets);
      }
      updatePointerModeUi();
      draw();
    }
    function toggleStatusPopover(name) {
      const popover = $(statusPopoverIds[name]);
      setStatusPopover(name, !popover || popover.hidden);
    }
    function isLocalizationMapInteraction(target) {
      return !!(
        state.localizationPopoverOpen
        && target
        && target.closest
        && target.closest(".canvas-box")
      );
    }
    function sleepMs(ms) {
      return new Promise(resolve => setTimeout(resolve, ms));
    }
    function preflightStatusText(result) {
      if (!result) return "尚未自检";
      const ageText = result.age_sec === null || result.age_sec === undefined ? "" : ` / ${fmtAge(result.age_sec)}前`;
      if (result.running) return `${result.summary || "基础自检后台执行中，请稍候"}${ageText}`;
      if (result.summary) return `${result.summary}${ageText}`;
      if (result.ok && result.navigation_ready === false) return `最近一次基础自检通过；导航待重定位${ageText}`;
      if (result.ok) return `最近一次基础自检通过${ageText}`;
      return `最近一次基础自检未通过${ageText}`;
    }
    function preflightTopLabel(result) {
      if (!result) return "尚未自检";
      if (result.running) return "自检中";
      if (result.ok) return "通过";
      const failures = Number(result.failures);
      if (Number.isFinite(failures) && failures > 0) return `失败 ${failures}项`;
      return "异常";
    }
    function renderPreflight(result) {
      state.preflight = result || null;
      const preflightTop = $("preflightTopStatus");
      if (preflightTop) {
        preflightTop.textContent = preflightTopLabel(result);
        preflightTop.title = preflightStatusText(result);
      }
      const summaries = [$("preflightSummary"), $("taskPreflightSummary")];
      for (const box of summaries) {
        if (!box) continue;
        box.className = "preflight-summary";
        if (result) {
          const cls = result.running ? "warn" : (result.ok ? "ok" : "fail");
          box.classList.add(cls);
        }
        box.textContent = preflightStatusText(result);
      }
      const countsBox = $("preflightCounts");
      if (countsBox) {
        if (!result) {
          countsBox.innerHTML = "";
        } else {
          const failures = Number.isFinite(Number(result.failures)) ? Number(result.failures) : 0;
          const warnings = Number.isFinite(Number(result.warnings)) ? Number(result.warnings) : 0;
          const items = Array.isArray(result.items) ? result.items : [];
          const passed = items.filter(item => item.status === "ok" || item.status === "info").length;
          countsBox.innerHTML = `
            <span class="preflight-count ok">通过 ${passed}</span>
            <span class="preflight-count warn">提醒 ${warnings}</span>
            <span class="preflight-count fail">失败 ${failures}</span>`;
        }
      }
      const itemsBox = $("preflightItems");
      if (itemsBox) {
        itemsBox.innerHTML = "";
        const items = result && result.items ? result.items : [];
        if (!items.length) {
          itemsBox.innerHTML = `<div class="small">尚未自检。</div>`;
        } else {
          for (const item of items) {
            const row = document.createElement("div");
            row.className = "check-row";
            const statusClass = item.status === "ok" ? "ok" : (item.status === "warn" ? "warn" : (item.status === "info" ? "ok" : "fail"));
            const statusText = item.status === "ok" ? "通过" : (item.status === "warn" ? "提醒" : (item.status === "info" ? "信息" : "失败"));
            row.innerHTML = `
              <div class="check-status ${statusClass}">${statusText}</div>
              <div><strong>${escapeHtml(item.label || item.key)}</strong><div class="small">${escapeHtml(item.message || "")}</div></div>
            `;
            itemsBox.appendChild(row);
          }
        }
      }
      if ($("preflightRaw")) $("preflightRaw").textContent = result ? JSON.stringify(result, null, 2) : "等待自检";
    }
    function normalizedTaskStatus(status) {
      return String(status || "ready");
    }
    function taskStatusAllowsStart(status) {
      const normalized = normalizedTaskStatus(status);
      return normalized === "ready" || normalized === "stopped" || normalized === "completed" || normalized === "error";
    }
    function taskStartLabelForStatus(status) {
      const normalized = normalizedTaskStatus(status);
      if (normalized === "error") return "从头重试";
      if (normalized === "invalid") return "任务无效";
      if (normalized === "running") return "执行中";
      if (!taskStatusAllowsStart(normalized)) return "不可执行";
      if (normalized === "completed") return "重新执行";
      if (normalized === "stopped") return "从头执行";
      return "开始执行";
    }
    function taskBelongsToSelectedMap(task) {
      const selected = String(effectiveCurrentMapId() || "");
      if (!selected || !task) return false;
      if (String(task.map_id || "") === selected) return true;
      const mapIds = Array.isArray(task.map_ids) ? task.map_ids.map(item => String(item || "")) : [];
      return mapIds.includes(selected);
    }
    function taskMapMismatchText(task) {
      if (taskBelongsToSelectedMap(task)) return "";
      const effectiveMapId = effectiveCurrentMapId();
      const selected = state.maps.find(item => String(item.id || "") === String(effectiveMapId || ""));
      const selectedName = selected ? (selected.name || selected.id) : (effectiveMapId || "-");
      return `该任务属于 ${task.map_id || "-"}，当前地图是 ${selectedName}；请在当前地图重新标点生成任务`;
    }
    function taskStatusBlockText(status) {
      const normalized = normalizedTaskStatus(status);
      if (normalized === "error") return "";
      if (normalized === "invalid") return "任务点位已失效，请重新生成任务";
      if (normalized === "running") return "任务正在执行中";
      if (!taskStatusAllowsStart(normalized)) return `任务状态 ${normalized} 不允许启动`;
      return "";
    }
    function taskDisplayStatus(taskStatus, multiFloor, mapMismatchText) {
      if (mapMismatchText) return "旧地图";
      if (multiFloor) return "跨楼层";
      if (taskStatus === "running") return "执行中";
      if (taskStatus === "invalid") return "无效";
      if (taskStatusAllowsStart(taskStatus)) return "可执行";
      return "不可执行";
    }
    function taskWaypointText(point, index) {
      if (!point) return `${index + 1}. -`;
      const pose = point.pose || {};
      const name = point.missing ? `${point.id || "缺失点"}(缺失)` : (point.label || point.id || `点${index + 1}`);
      const xy = Number.isFinite(Number(pose.x)) && Number.isFinite(Number(pose.y))
        ? ` x${fmtNumber(Number(pose.x), 2)} y${fmtNumber(Number(pose.y), 2)}`
        : "";
      const yaw = Number.isFinite(Number(pose.yaw)) ? ` yaw${fmtNumber(Number(pose.yaw), 2)}` : "";
      const dwell = Number.isFinite(Number(point.dwell_s)) ? ` 停${fmtNumber(Number(point.dwell_s), 1)}s` : "";
      return `${index + 1}.${point.floor || "-"} ${name}${xy}${yaw}${dwell}`;
    }
    function taskStartRequest(task) {
      const waypoints = Array.isArray(task.waypoints) ? task.waypoints : [];
      const first = waypoints.length ? waypoints[0] : null;
      return {
        task_id: task.id,
        expected_annotation_ids: Array.isArray(task.annotation_ids) ? task.annotation_ids.slice() : [],
        expected_first_annotation_id: first ? first.id : ((task.annotation_ids || [])[0] || ""),
        expected_first_pose: first && first.pose ? first.pose : null,
        expected_map_id: task.map_id || "",
        expected_task_updated_at: task.updated_at || task.created_at || "",
      };
    }
    function taskStartConfirmText(task, taskNote) {
      const waypoints = Array.isArray(task.waypoints) ? task.waypoints : [];
      const first = waypoints.length ? waypoints[0] : null;
      const sequence = waypoints.length
        ? waypoints.map((point, index) => taskWaypointText(point, index)).join(" → ")
        : "无点位";
      return [
        `确认开始任务：${task.name || task.id}`,
        `首点：${first ? taskWaypointText(first, 0) : "-"}`,
        `顺序：${sequence}`,
        `状态：${taskNote}`,
        `确认：已完成自检、地图/定位/点云现场检查`,
        "确认后机器狗会立即向首点导航。"
      ].filter(Boolean).join("\n");
    }
    function activeRadarStatus(activeTask, waypoint) {
      const radar = state.latest && state.latest.radar_inspection && state.latest.radar_inspection.parsed;
      if (!radar || typeof radar !== "object") return null;
      const runId = String((activeTask && activeTask.run_id) || (waypoint && waypoint.run_id) || "").trim();
      const radarRunId = String(radar.run_id || "").trim();
      if (runId && radarRunId && runId !== radarRunId) return null;
      const expectedKey = runId && waypoint && waypoint.waypoint && activeTask
        ? `${runId}:${activeTask.task_id || "manual"}:${Number(activeTask.index) || 0}:${waypoint.waypoint.id || waypoint.waypoint.label || "waypoint"}`
        : "";
      if (expectedKey && radar.waypoint_key && String(radar.waypoint_key) !== expectedKey) return null;
      return radar;
    }
    function taskPhaseText(activeTask, waypoint) {
      const phase = String((waypoint && waypoint.phase) || (activeTask && activeTask.phase) || "navigating");
      const wp = waypoint && waypoint.waypoint ? waypoint.waypoint : {};
      const radarPlan = wp.radar && typeof wp.radar === "object" ? wp.radar : {};
      if (phase === "dwelling" && radarPlan.enabled === true) {
        const radar = activeRadarStatus(activeTask, waypoint);
        const status = radar && String(radar.status || radar.state || "");
        if (!status || ["starting", "waiting_for_device"].includes(status)) return "等待雷达开始扫描";
        if (status === "running") {
          const progress = Number(radar.progress);
          return Number.isFinite(progress) ? `雷达扫描中 ${progress}%` : "雷达扫描中";
        }
        if (["scan_complete", "analysis_pending", "analyzing"].includes(status)) return "等待雷达返回结果";
        if (status === "communication_retry") return "雷达通信重试中";
        if (["completed", "finished", "complete"].includes(status)) return "雷达检测完成，准备继续";
        if (["failed", "error"].includes(status)) return "雷达检测失败";
        return `雷达 ${status}`;
      }
      if (phase === "dwelling") return "停留/检测";
      if (phase === "charging") {
        const chargeStatus = String(
          (activeTask && activeTask.charge_command_status) || "pending"
        ).toLowerCase();
        if (chargeStatus === "accepted") return "原厂已接受充电导航";
        return "已到达充电点，正在请求原厂充电";
      }
      if (phase === "cross_floor") return "跨楼层切换";
      if (phase === "completed") return "任务完成";
      if (activeTask && activeTask.status_message && activeTask.last_nav_goal_status === "idle") return activeTask.status_message;
      return "导航中";
    }
    function taskTopStatusText(activeTask, waypoint) {
      if (!activeTask || activeTask.status !== "running") return "空闲";
      const total = Array.isArray(activeTask.annotation_ids) ? activeTask.annotation_ids.length : 0;
      const index = Math.max(0, Number(activeTask.index) || 0);
      const phase = taskPhaseText(activeTask, waypoint);
      return total ? `第 ${Math.min(index + 1, total)} / ${total} 点 · ${phase}` : phase;
    }
    const teleopDirectionAxes = {
      forward: {linear_x: 1, linear_y: 0, angular_z: 0},
      backward: {linear_x: -1, linear_y: 0, angular_z: 0},
      left: {linear_x: 0, linear_y: 1, angular_z: 0},
      right: {linear_x: 0, linear_y: -1, angular_z: 0},
      rotate_left: {linear_x: 0, linear_y: 0, angular_z: 1},
      rotate_right: {linear_x: 0, linear_y: 0, angular_z: -1}
    };
    const teleopKeyDirections = {
      w: "forward",
      ArrowUp: "forward",
      s: "backward",
      ArrowDown: "backward",
      a: "left",
      ArrowLeft: "left",
      d: "right",
      ArrowRight: "right",
      q: "rotate_left",
      e: "rotate_right"
    };
    function teleopOwnsSession(serverState = null) {
      const teleop = serverState || (state.latest && state.latest.teleoperation) || {};
      return Boolean(state.teleop.sessionId && teleop.active);
    }
    function clearLocalTeleop() {
      if (state.teleop.heartbeatTimer !== null) {
        clearInterval(state.teleop.heartbeatTimer);
        state.teleop.heartbeatTimer = null;
      }
      state.teleop.sessionId = null;
      state.teleop.axes = {linear_x: 0, linear_y: 0, angular_z: 0};
      state.teleop.pointers.clear();
      state.teleop.keys.clear();
      state.teleop.pendingCommand = false;
      state.teleop.requestInFlight = false;
      state.teleop.releasing = false;
      for (const button of document.querySelectorAll("[data-teleop-direction]")) {
        button.classList.remove("is-active");
      }
    }
    const motionStateLabels = {
      0: "空闲",
      1: "站立",
      2: "关节阻尼",
      3: "开机阻尼",
      4: "趴下",
      6: "标准运动",
      8: "敏捷运动"
    };
    function currentMotionState(snapshot = state.latest) {
      const sample = snapshot && snapshot.motion_state;
      const motionState = sample ? Number(sample.state) : NaN;
      const lastUpdate = sample ? Number(sample.last_update) : NaN;
      const now = snapshot && Number.isFinite(Number(snapshot.node_time))
        ? Number(snapshot.node_time)
        : Date.now() / 1000;
      const age = Number.isFinite(lastUpdate) ? Math.max(0, now - lastUpdate) : Infinity;
      return {
        state: motionState,
        age,
        fresh: Object.prototype.hasOwnProperty.call(motionStateLabels, motionState) && age <= 3.0,
        label: Object.prototype.hasOwnProperty.call(motionStateLabels, motionState) ? motionStateLabels[motionState] : "未知"
      };
    }
    function renderTeleoperation(teleop) {
      const payload = teleop || {};
      if (state.teleop.sessionId && payload.active === false) clearLocalTeleop();
      const owns = teleopOwnsSession(payload);
      const occupied = Boolean(payload.active && !owns);
      const top = $("teleopTopStatus");
      if (top) top.textContent = owns ? "接管中" : (occupied ? "已被接管" : "未接管");
      const summary = $("teleopStatusSummary");
      if (summary) {
        const muxMode = String(payload.mux_mode || "unknown");
        const heartbeat = Number(payload.heartbeat_age_s);
        const heartbeatText = Number.isFinite(heartbeat) ? ` / 心跳 ${heartbeat.toFixed(2)}s` : "";
        const motion = currentMotionState();
        const postureText = motion.fresh ? ` / 姿态 ${motion.label}` : " / 姿态状态未知";
        const leaseExpired = !payload.active && payload.last_stop_reason === "browser_lease_timeout";
        summary.className = `compact-status${(payload.active && muxMode !== "teleop") || leaseExpired ? " fail" : ""}`;
        if (owns) summary.textContent = `人工接管中 / 仲裁 ${muxMode}${heartbeatText}${postureText}`;
        else if (occupied) summary.textContent = `其他操作端已接管 / 仲裁 ${muxMode}${heartbeatText}${postureText}`;
        else if (leaseExpired) summary.textContent = "遥控会话已超时，请重新接管";
        else if (!payload.available) summary.textContent = "速度仲裁器未就绪，遥控不可用";
        else summary.textContent = `自主导航 / 仲裁 ${muxMode}${postureText}`;
      }
      const limits = payload.limits || {};
      if ($("teleopLimits")) {
        $("teleopLimits").textContent = `限速：前进 ${fmtNumber(Number(limits.forward_mps), 2)} m/s / 后退 ${fmtNumber(Number(limits.reverse_mps), 2)} m/s / 横移 ${fmtNumber(Number(limits.lateral_mps), 2)} m/s / 旋转 ${fmtNumber(Number(limits.angular_radps), 2)} rad/s`;
      }
      for (const button of document.querySelectorAll(".teleop-control")) button.disabled = !owns;
      for (const button of document.querySelectorAll("[data-teleop-posture-action]")) {
        button.disabled = !owns;
      }
      const gaitInfo = payload.gait || {};
      const gaitNames = {flat: "平地", stairs: "楼梯"};
      for (const button of document.querySelectorAll("[data-teleop-gait]")) {
        button.disabled = !owns;
        button.classList.toggle("active", owns && gaitInfo.last_command === button.dataset.teleopGait);
      }
      const gaitStatus = $("teleopGaitStatus");
      if (gaitStatus) {
        if (gaitInfo.last_command && gaitNames[gaitInfo.last_command]) {
          const failed = String(gaitInfo.last_result || "").startsWith("failed");
          gaitStatus.textContent = failed
            ? `${gaitNames[gaitInfo.last_command]}切换失败`
            : `当前：${gaitNames[gaitInfo.last_command]}`;
        } else {
          gaitStatus.textContent = "当前：默认";
        }
      }
      if ($("acquireTeleopBtn")) {
        $("acquireTeleopBtn").disabled = Boolean(payload.active || payload.acquiring || !payload.available);
      }
      if ($("releaseTeleopBtn")) $("releaseTeleopBtn").disabled = !owns;
    }
    function renderBatteryStatus(snapshot) {
      const battery = snapshot && snapshot.battery ? snapshot.battery : {};
      const packs = Array.isArray(battery.packs) ? battery.packs : [];
      const primary = battery.primary || packs[0] || null;
      const summary = $("batteryStatusSummary");
      const detail = $("batteryStatusDetail");
      if (!summary || !detail) return;
      if (!primary) {
        summary.textContent = "暂未收到电池数据";
        detail.textContent = "等待原厂电池话题和运动状态反馈";
        return;
      }
      const level = Number(primary.level);
      const reportedCount = Number(battery.count);
      const packCount = Number.isFinite(reportedCount) ? Math.max(0, Math.round(reportedCount)) : packs.length;
      summary.textContent = `主电池 ${Number.isFinite(level) ? `${level}%` : "-"} / ${packCount} 组电池`;
      const temperature = Number(primary.temperature_c);
      const age = battery.last_update ? `${fmtAge(Math.max(0, Number(snapshot.node_time || Date.now() / 1000) - Number(battery.last_update)))}前` : "-";
      const current = Number(primary.current_a);
      const currentText = Number.isFinite(current)
        ? (current > 0.1 ? "疑似充电电流" : (current < -0.1 ? "放电电流" : "电流接近零"))
        : "充电状态未知";
      detail.innerHTML = [
        `<div>电压 ${fmtNumber(Number(primary.voltage_v), 1)} V / 电流 ${fmtNumber(Number(primary.current_a), 1)} A</div>`,
        `<div>温度 ${Number.isFinite(temperature) ? `${fmtNumber(temperature, 1)} ℃` : "-"} / 循环 ${text(primary.cycles)} 次</div>`,
        `<div>电池 MOS 状态：${text(primary.mos_state)} / 保护状态：${text(primary.protected_state)}</div>`,
        `<div>充电判断：${escapeHtml(currentText)}（原厂未提供独立充电状态字段）</div>`,
        `<div>电池数据更新时间：${escapeHtml(age)}</div>`
      ].join("");
    }
    async function loadTeleopStatus() {
      const payload = await fetchJson("/api/teleop/state");
      state.latest = {...(state.latest || {}), teleoperation: payload.teleoperation || {}};
      renderTeleoperation(payload.teleoperation || {});
      return payload.teleoperation || {};
    }
    function recomputeTeleopAxes() {
      const directions = [...state.teleop.pointers.values(), ...state.teleop.keys.values()];
      const axes = {linear_x: 0, linear_y: 0, angular_z: 0};
      for (const direction of directions) {
        const value = teleopDirectionAxes[direction];
        if (!value) continue;
        axes.linear_x += value.linear_x;
        axes.linear_y += value.linear_y;
        axes.angular_z += value.angular_z;
      }
      axes.linear_x = Math.max(-1, Math.min(1, axes.linear_x));
      axes.linear_y = Math.max(-1, Math.min(1, axes.linear_y));
      axes.angular_z = Math.max(-1, Math.min(1, axes.angular_z));
      state.teleop.axes = axes;
      const activeDirections = new Set(directions);
      for (const button of document.querySelectorAll("[data-teleop-direction]")) {
        button.classList.toggle("is-active", activeDirections.has(button.dataset.teleopDirection));
      }
    }
    async function sendTeleopCommand() {
      const sessionId = state.teleop.sessionId;
      if (!sessionId || state.teleop.releasing) return;
      if (state.teleop.requestInFlight) {
        state.teleop.pendingCommand = true;
        return;
      }
      state.teleop.requestInFlight = true;
      state.teleop.pendingCommand = false;
      const sequence = state.teleop.sequence++;
      const axes = {...state.teleop.axes};
      try {
        await api("POST", "/api/teleop/command", {
          session_id: sessionId,
          sequence,
          ...axes
        });
      } catch (err) {
        if (state.teleop.sessionId === sessionId && !state.teleop.releasing) {
          clearLocalTeleop();
          renderTeleoperation({
            active: false,
            available: Boolean(state.latest && state.latest.teleoperation && state.latest.teleoperation.available),
            last_stop_reason: "command_failed",
            limits: (state.latest && state.latest.teleoperation && state.latest.teleoperation.limits) || {}
          });
          showOperationFeedback("遥控已停止", err, true);
        }
      } finally {
        state.teleop.requestInFlight = false;
        if (state.teleop.pendingCommand && !state.teleop.releasing && state.teleop.sessionId === sessionId) {
          state.teleop.pendingCommand = false;
          sendTeleopCommand();
        }
      }
    }
    function startTeleopHeartbeat(timeoutSeconds) {
      if (state.teleop.heartbeatTimer !== null) clearInterval(state.teleop.heartbeatTimer);
      const timeoutMs = Number(timeoutSeconds) * 1000;
      const intervalMs = Math.max(75, Math.min(120, Number.isFinite(timeoutMs) ? timeoutMs / 3 : 100));
      state.teleop.heartbeatTimer = setInterval(sendTeleopCommand, intervalMs);
      sendTeleopCommand();
    }
    function zeroTeleopMotion() {
      state.teleop.pointers.clear();
      state.teleop.keys.clear();
      recomputeTeleopAxes();
      sendTeleopCommand();
    }
    async function acquireTeleop() {
      if (!window.confirm("确认人工接管？\n\n当前自主任务会立即终止，结束接管后不会自动恢复。")) return;
      const button = $("acquireTeleopBtn");
      button.disabled = true;
      try {
        const payload = await api("POST", "/api/teleop/acquire", {confirm: true});
        state.teleop.sessionId = payload.session_id;
        state.teleop.sequence = 0;
        state.teleop.axes = {linear_x: 0, linear_y: 0, angular_z: 0};
        state.latest = {...(state.latest || {}), teleoperation: payload.teleoperation || {active: true}};
        renderTeleoperation(payload.teleoperation || {active: true, available: true});
        startTeleopHeartbeat((payload.teleoperation || {}).command_timeout_s);
      } catch (err) {
        showOperationFeedback("人工接管失败", err, true);
        loadTeleopStatus().catch(console.warn);
      } finally {
        button.disabled = false;
      }
    }
    async function releaseTeleop({silent = false, closePopover = false} = {}) {
      const sessionId = state.teleop.sessionId;
      if (!sessionId || state.teleop.releasing) {
        if (closePopover) setStatusPopover("", false);
        return;
      }
      state.teleop.releasing = true;
      zeroTeleopMotion();
      try {
        const payload = await api("POST", "/api/teleop/release", {session_id: sessionId});
        state.latest = {...(state.latest || {}), teleoperation: payload.teleoperation || {active: false}};
      } catch (err) {
        if (!silent) showOperationFeedback("结束接管异常", err, true);
      } finally {
        clearLocalTeleop();
        renderTeleoperation((state.latest && state.latest.teleoperation) || {active: false});
        if (closePopover) setStatusPopover("", false);
      }
    }
    async function sendTeleopMotionState(action) {
      const labels = {stand: "起立", lie: "趴下"};
      if (!Object.prototype.hasOwnProperty.call(labels, action)) {
        showOperationFeedback("遥控动作无效", "未知的起立/趴下动作。", true);
        return;
      }
      if (!state.teleop.sessionId) {
        showOperationFeedback("请先人工接管", "起立/趴下属于主动运动状态切换，需要先取得当前网页遥控会话。", true);
        return;
      }
      const label = labels[action];
      if (!await requestTeleopConfirmation(`确认${label}`, `动作执行期间遥控保持，速度指令自动清零；原厂姿态过渡期运动控制本就禁用，动作完成后可直接继续遥控。\n\n确认执行${label}？`)) return;
      const buttons = [...document.querySelectorAll("[data-teleop-posture-action]")];
      for (const button of buttons) button.disabled = true;
      for (const button of document.querySelectorAll("[data-teleop-gait]")) button.disabled = true;
      // Keep the session and the heartbeat: during posture transitions the
      // robot ignores velocity commands, so zeroed heartbeats are inert and
      // keep the lease alive; the operator continues right after the action.
      zeroTeleopMotion();
      try {
        const payload = await api("POST", "/api/teleop/motion", {
          action,
          session_id: state.teleop.sessionId || ""
        });
        state.latest = {...(state.latest || {}), teleoperation: payload.teleoperation || {active: true}};
        renderTeleoperation(payload.teleoperation || {active: true});
      } catch (err) {
        showOperationFeedback(`${label}失败`, err, true);
        loadTeleopStatus().catch(console.warn);
      } finally {
        renderTeleoperation((state.latest && state.latest.teleoperation) || {active: true});
      }
    }
    async function sendTeleopGait(gait) {
      const names = {flat: "平地步态", stairs: "楼梯步态"};
      const label = names[gait];
      if (!label) return;
      if (!state.teleop.sessionId) {
        showOperationFeedback("请先人工接管", "切换步态需要先取得当前网页遥控会话。", true);
        return;
      }
      for (const button of document.querySelectorAll("[data-teleop-gait]")) button.disabled = true;
      try {
        const payload = await api("POST", "/api/teleop/gait", {
          gait,
          session_id: state.teleop.sessionId || ""
        });
        state.latest = {...(state.latest || {}), teleoperation: payload.teleoperation || {active: true}};
        renderTeleoperation(payload.teleoperation || {active: true});
      } catch (err) {
        showOperationFeedback(`切换${label}失败`, err, true);
        loadTeleopStatus().catch(console.warn);
      }
    }
    async function softEmergencyStopTeleop() {
      if (!await requestTeleopConfirmation("确认软急停", "机器狗将切换到关节阻尼状态，网页遥控和自主任务都会锁定。\n\n确认执行软急停？")) return;
      const button = $("teleopSoftStopBtn");
      if (button) button.disabled = true;
      state.teleop.releasing = true;
      state.teleop.pendingCommand = false;
      if (state.teleop.heartbeatTimer !== null) {
        clearInterval(state.teleop.heartbeatTimer);
        state.teleop.heartbeatTimer = null;
      }
      try {
        const payload = await api("POST", "/api/teleop/motion", {
          action: "soft_stop",
          session_id: state.teleop.sessionId || ""
        });
        clearLocalTeleop();
        state.latest = {...(state.latest || {}), teleoperation: payload.teleoperation || {active: false}};
        renderTeleoperation(payload.teleoperation || {active: false});
        showOperationFeedback("软急停", payload);
      } catch (err) {
        clearLocalTeleop();
        showOperationFeedback("软急停失败", err, true);
        loadTeleopStatus().catch(console.warn);
      } finally {
        if (button) button.disabled = false;
      }
    }
    async function oneKeyCharge() {
      if (!window.confirm("确认启动一键充电？\n\n系统会执行当前地图的充电点任务；当前自主任务必须先停止。")) return;
      const button = $("oneKeyChargeBtn");
      if (button) button.disabled = true;
      try {
        const payload = await api("POST", "/api/charge/one_key", {});
        showOperationFeedback("一键充电", payload);
        updateState(await fetchJson("/api/state"));
      } catch (err) {
        showOperationFeedback("一键充电失败", err, true);
      } finally {
        if (button) button.disabled = false;
      }
    }
    function renderActiveTaskSummary(activeTask, waypoint) {
      const box = $("activeTaskSummary");
      if (!box) return;
      box.className = "preflight-summary";
      if (!activeTask && !waypoint) {
        box.textContent = "无任务";
        return;
      }
      const source = waypoint || {};
      const wp = source.waypoint || {};
      const parts = [];
      if (activeTask && activeTask.task_name) parts.push(activeTask.task_name);
      if (wp.label) parts.push(`点位 ${wp.label}`);
      if (Number.isFinite(Number(source.index))) parts.push(`序号 ${Number(source.index) + 1}`);
      if (source.phase || activeTask) parts.push(taskPhaseText(activeTask, source));
      if (source.nav_goal_status) parts.push(`导航 ${source.nav_goal_status}`);
      if (Number.isFinite(Number(source.distance_m))) parts.push(`距离 ${fmtNumber(Number(source.distance_m), 2)}m`);
      const navFeedback = source.nav_feedback || (activeTask && activeTask.last_nav_feedback) || null;
      const navGoalMatch = source.nav_goal_match || (activeTask && activeTask.last_nav_goal_match) || null;
      if (navFeedback) {
        if (navFeedback.goal_seq !== undefined && navFeedback.goal_seq !== null) {
          parts.push(`导航序号 ${navFeedback.goal_seq}`);
        }
        if (Number.isFinite(Number(source.nav_feedback_age_s))) {
          parts.push(`导航反馈 ${fmtAge(Number(source.nav_feedback_age_s))}前`);
        }
        if (Number.isFinite(Number(navFeedback.distance_remaining))) {
          parts.push(`导航剩余 ${fmtNumber(Number(navFeedback.distance_remaining), 2)}m`);
        }
        if (Number.isFinite(Number(navFeedback.navigation_time))) {
          parts.push(`导航 ${fmtNumber(Number(navFeedback.navigation_time), 0)}s`);
        }
        if (Number.isFinite(Number(navFeedback.recoveries)) && Number(navFeedback.recoveries) > 0) {
          parts.push(`恢复 ${Number(navFeedback.recoveries)}次`);
        }
      }
      if (source.goal_attempt_id || (activeTask && activeTask.last_goal_attempt_id)) {
        parts.push(`尝试 ${(source.goal_attempt_id || activeTask.last_goal_attempt_id)}`);
      }
      const floorGoalPublishedAt = source.last_floor_goal_published_at || (activeTask && activeTask.last_floor_goal_published_at);
      if (floorGoalPublishedAt) parts.push(`floor_goal已发 ${floorGoalPublishedAt}`);
      const floorGoalCross = source.last_floor_goal_cross_floor !== undefined
        ? source.last_floor_goal_cross_floor
        : (activeTask && activeTask.last_floor_goal_cross_floor);
      const floorGoalSource = source.last_floor_goal_source_floor || (activeTask && activeTask.last_floor_goal_source_floor);
      const floorGoalTarget = source.last_floor_goal_target_floor || (activeTask && activeTask.last_floor_goal_target_floor);
      if (floorGoalCross && floorGoalSource && floorGoalTarget) {
        parts.push(`跨楼层 ${floorGoalSource}->${floorGoalTarget}`);
      }
      const floorGoalPublishes = source.floor_goal_publish_count !== undefined
        ? source.floor_goal_publish_count
        : (activeTask && activeTask.floor_goal_publish_count);
      if (Number.isFinite(Number(floorGoalPublishes))) parts.push(`/floor_goal ${Number(floorGoalPublishes)}次`);
      const transitionStatus = source.last_transition_nav_status || (activeTask && activeTask.last_transition_nav_status);
      const transitionLabel = source.last_transition_nav_label || (activeTask && activeTask.last_transition_nav_label);
      const transitionPayload = source.last_transition_nav_payload || (activeTask && activeTask.last_transition_nav_payload) || null;
      if (transitionLabel) parts.push(`楼梯阶段 ${transitionLabel}`);
      if (transitionPayload && Number.isFinite(Number(transitionPayload.distance_remaining))) {
        parts.push(`楼梯剩余 ${fmtNumber(Number(transitionPayload.distance_remaining), 2)}m`);
      } else if (transitionStatus) {
        parts.push(`楼梯状态 ${transitionStatus}`);
      }
      if (navGoalMatch) {
        if (navGoalMatch.nav_goal_seq !== undefined && navGoalMatch.nav_goal_seq !== null && !(navFeedback && navFeedback.goal_seq !== undefined && navFeedback.goal_seq !== null)) {
          parts.push(`导航序号 ${navGoalMatch.nav_goal_seq}`);
        }
        if (navGoalMatch.matches === false) {
          parts.push(`目标不匹配 ${navGoalMatch.reason || ""}`.trim());
        }
      }
      const ignoredMatch = source.last_ignored_nav_goal_match || (activeTask && activeTask.last_ignored_nav_goal_match) || null;
      if (ignoredMatch && ignoredMatch.reason) parts.push(`已忽略旧反馈 ${ignoredMatch.reason}`);
      const robotPose = source.robot_pose || (activeTask && activeTask.last_robot_pose) || null;
      const statePose = source.state_pose || null;
      const goalPose = source.goal_pose || (wp && wp.pose) || null;
      if (robotPose && Number.isFinite(Number(robotPose.x)) && Number.isFinite(Number(robotPose.y))) {
        parts.push(`狗 x${fmtNumber(Number(robotPose.x), 2)} y${fmtNumber(Number(robotPose.y), 2)}`);
      }
      if (statePose && Number.isFinite(Number(statePose.x)) && Number.isFinite(Number(statePose.y)) && (!robotPose || planarError(robotPose, statePose) > 0.05)) {
        parts.push(`地图位姿 x${fmtNumber(Number(statePose.x), 2)} y${fmtNumber(Number(statePose.y), 2)}`);
      }
      if (goalPose && Number.isFinite(Number(goalPose.x)) && Number.isFinite(Number(goalPose.y))) {
        parts.push(`目标 x${fmtNumber(Number(goalPose.x), 2)} y${fmtNumber(Number(goalPose.y), 2)}`);
      }
      const navPose = navFeedbackPose(navFeedback);
      const robotGoalError = planarError(robotPose, goalPose);
      const navGoalError = planarError(navPose, goalPose);
      const robotNavError = planarError(robotPose, navPose);
      const stateNavError = planarError(statePose, navPose);
      const pathGoalError = Number(source.path_goal_error_m);
      if (Number.isFinite(robotGoalError)) parts.push(`狗差 ${fmtNumber(robotGoalError, 2)}m`);
      if (Number.isFinite(navGoalError)) parts.push(`导航差 ${fmtNumber(navGoalError, 2)}m`);
      if (Number.isFinite(robotNavError)) parts.push(`位姿差 ${fmtNumber(robotNavError, 2)}m`);
      if (Number.isFinite(stateNavError)) parts.push(`反馈差 ${fmtNumber(stateNavError, 2)}m`);
      if (Number.isFinite(pathGoalError)) parts.push(`路径差 ${fmtNumber(pathGoalError, 2)}m`);
      if (source.plan_goal_verified === true || (activeTask && activeTask.plan_goal_verified === true)) {
        parts.push("路径已校验");
      }
      const sentPathVersion = source.goal_sent_path_version !== undefined ? source.goal_sent_path_version : (activeTask && activeTask.goal_sent_path_version);
      const planPathVersion = source.plan_path_version !== undefined ? source.plan_path_version : (activeTask && activeTask.plan_path_version);
      if (sentPathVersion !== undefined && sentPathVersion !== null) parts.push(`下发路径版 ${sentPathVersion}`);
      if (planPathVersion !== undefined && planPathVersion !== null) parts.push(`校验路径版 ${planPathVersion}`);
      if (Number.isFinite(Number(source.remaining_dwell_s)) && Number(source.remaining_dwell_s) > 0) {
        parts.push(`剩余停留 ${fmtNumber(Number(source.remaining_dwell_s), 1)}s`);
      }
      if (Number.isFinite(Number(source.elapsed_s))) parts.push(`本点 ${fmtNumber(Number(source.elapsed_s), 0)}s`);
      if (Number.isFinite(Number(source.goal_send_count))) parts.push(`目标下发 ${Number(source.goal_send_count)}次`);
      const stallAge = source.stall_age_s !== undefined ? source.stall_age_s : (activeTask && activeTask.stall_age_s);
      if (Number.isFinite(Number(stallAge)) && Number(stallAge) > 0) {
        parts.push(`低进展 ${fmtNumber(Number(stallAge), 0)}s`);
      }
      const lastProgressAt = source.last_progress_at || (activeTask && activeTask.last_progress_at);
      if (lastProgressAt) parts.push(`最近进展 ${lastProgressAt}`);
      const msg = source.status_message || (activeTask && activeTask.status_message) || "";
      if (msg) parts.push(msg);
      const timeline = activeTask && Array.isArray(activeTask.timeline) ? activeTask.timeline : [];
      const lastEvent = timeline.length ? timeline[timeline.length - 1] : null;
      if (lastEvent && lastEvent.message) parts.push(`最近事件 ${lastEvent.message}`);
      box.classList.add((activeTask && activeTask.last_error) ? "fail" : "ok");
      box.textContent = parts.length ? parts.join(" / ") : "任务执行中";
    }
    function updateTaskControlButtons(payload = state.latest) {
      const stopBtn = $("stopTaskBtn");
      const resetBtn = $("resetTaskSessionBtn");
      const hasActiveTask = !!(payload && (payload.active_task || payload.active_waypoint));
      if (stopBtn) {
        stopBtn.disabled = false;
        stopBtn.title = hasActiveTask
          ? "停止当前前端任务"
          : "取消可能残留的导航目标并发送零速度";
      }
      if (resetBtn) {
        resetBtn.disabled = false;
        resetBtn.title = "显式复位导航会话；会停止前端任务、清理导航会话并清代价地图";
      }
    }
    function renderPoseTracker(targetId, payload = state.latest) {
      const box = $(targetId);
      if (!box) return;
      if (!payload) {
        box.textContent = "等待位姿";
        return;
      }
      const activeTask = payload.active_task || null;
      const waypoint = payload.active_waypoint && payload.active_waypoint.parsed ? payload.active_waypoint.parsed : null;
      const wp = waypoint && waypoint.waypoint ? waypoint.waypoint : null;
      const goalPose = (waypoint && waypoint.goal_pose) || (wp && wp.pose) || (activeTask && activeTask.last_goal_pose) || null;
      const navFeedback = (waypoint && waypoint.nav_feedback) || (activeTask && activeTask.last_nav_feedback) || null;
      const navPose = navFeedbackPose(navFeedback);
      const robotPose = (waypoint && waypoint.robot_pose) || (activeTask && activeTask.last_robot_pose) || payload.pose || null;
      const currentFresh = hasFreshPose(payload);
      const poseAge = poseAgeSec(payload);
      const rows = [];
      const addRow = (label, value, cls = "") => {
        rows.push(`<div class="pose-track-row ${cls}"><strong>${label}</strong><span>${value}</span></div>`);
      };
      const poseCls = payload.localization_ok === true && currentFresh ? "ok" : (payload.localization_ok === false ? "fail" : "warn");
      if (payload.pose) {
        const ageText = poseAge === null || poseAge === undefined ? "" : ` / ${currentFresh ? "实时" : "过期"} ${fmtAge(poseAge)}前`;
        addRow("地图位姿", `${fmtPose(payload.pose, 180 / Math.PI)}${ageText}`, poseCls);
      } else {
        addRow("地图位姿", poseUnavailableText(payload), poseCls);
      }
      if (navPose && Number.isFinite(Number(navPose.x)) && Number.isFinite(Number(navPose.y))) {
        const age = waypoint && Number.isFinite(Number(waypoint.nav_feedback_age_s)) ? ` / ${fmtAge(Number(waypoint.nav_feedback_age_s))}前` : "";
        addRow("导航反馈", `${fmtPose(navPose, 180 / Math.PI)}${age}`, "ok");
      } else {
        addRow("导航反馈", activeTask || waypoint ? "等待当前目标反馈" : "无活动任务", activeTask || waypoint ? "warn" : "");
      }
      if (goalPose && Number.isFinite(Number(goalPose.x)) && Number.isFinite(Number(goalPose.y))) {
        const goalName = wp && (wp.label || wp.id) ? ` / ${wp.label || wp.id}` : "";
        addRow("当前目标", `${fmtPose(goalPose)}${goalName}`, "ok");
      } else {
        addRow("当前目标", activeTask || waypoint ? "等待目标下发" : "无活动任务", activeTask || waypoint ? "warn" : "");
      }
      const robotGoalError = planarError(robotPose, goalPose);
      const navGoalError = planarError(navPose, goalPose);
      const robotNavError = planarError(robotPose, navPose);
      const metricParts = [];
      if (Number.isFinite(robotGoalError)) metricParts.push(`狗-目标 ${fmtNumber(robotGoalError, 2)}m`);
      if (Number.isFinite(navGoalError)) metricParts.push(`导航-目标 ${fmtNumber(navGoalError, 2)}m`);
      if (Number.isFinite(robotNavError)) metricParts.push(`狗-导航 ${fmtNumber(robotNavError, 2)}m`);
      if (waypoint && Number.isFinite(Number(waypoint.path_goal_error_m))) metricParts.push(`路径-目标 ${fmtNumber(Number(waypoint.path_goal_error_m), 2)}m`);
      if (waypoint && waypoint.plan_goal_verified === true) metricParts.push("路径已校验");
      addRow("误差", metricParts.length ? metricParts.join(" / ") : "等待任务目标和反馈", metricParts.length ? "ok" : "");
      const phaseParts = [];
      if (activeTask && activeTask.task_name) phaseParts.push(activeTask.task_name);
      if (waypoint && waypoint.phase) phaseParts.push(waypoint.phase === "dwelling" ? "停留中" : "导航中");
      if (waypoint && waypoint.nav_goal_status) phaseParts.push(`导航 ${waypoint.nav_goal_status}`);
      if (waypoint && Number.isFinite(Number(waypoint.distance_m))) phaseParts.push(`距离 ${fmtNumber(Number(waypoint.distance_m), 2)}m`);
      addRow("任务阶段", phaseParts.length ? phaseParts.join(" / ") : "无活动任务", activeTask || waypoint ? "ok" : "");
      box.innerHTML = rows.join("");
    }
    function topicPayload(sample) {
      if (!sample) return null;
      if (sample.parsed && typeof sample.parsed === "object") return sample.parsed;
      if (sample.raw && typeof sample.raw === "object") return sample.raw;
      if (typeof sample.raw === "string") {
        try { return JSON.parse(sample.raw); } catch (_err) { return null; }
      }
      return typeof sample === "object" ? sample : null;
    }
    function drawYoloOverlay(snapshot) {
      const canvas = $("frontYoloOverlay");
      if (!canvas) return;
      const ctx = canvas.getContext("2d");
      const rect = canvas.getBoundingClientRect();
      const width = Math.max(1, Math.round(rect.width));
      const height = Math.max(1, Math.round(rect.height));
      const dpr = Math.max(1, Number(window.devicePixelRatio) || 1);
      if (canvas.width !== Math.round(width * dpr) || canvas.height !== Math.round(height * dpr)) {
        canvas.width = Math.round(width * dpr);
        canvas.height = Math.round(height * dpr);
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, width, height);
      if (!cameraViewers.front.active) return;
      const status = topicPayload(snapshot && snapshot.inspection_status) || {};
      if (status.enabled !== true || status.ready !== true) return;
      const payload = topicPayload(snapshot && snapshot.detections) || {};
      const rows = Array.isArray(payload.detections) ? payload.detections : [];
      const sourceWidth = Number(payload.image_width) || 1280;
      const sourceHeight = Number(payload.image_height) || 720;
      const scale = Math.min(width / sourceWidth, height / sourceHeight);
      const offsetX = (width - sourceWidth * scale) * 0.5;
      const offsetY = (height - sourceHeight * scale) * 0.5;
      ctx.lineWidth = 2;
      ctx.font = "600 13px system-ui, sans-serif";
      for (const item of rows.slice(0, 50)) {
        const box = Array.isArray(item.bbox_xyxy) ? item.bbox_xyxy.map(Number) : [];
        if (box.length !== 4 || box.some(value => !Number.isFinite(value))) continue;
        const x = offsetX + box[0] * scale;
        const y = offsetY + box[1] * scale;
        const w = Math.max(1, (box[2] - box[0]) * scale);
        const h = Math.max(1, (box[3] - box[1]) * scale);
        const confidence = Number(item.confidence);
        const label = `${item.class_name || `类别 ${item.class_id ?? "-"}`}${Number.isFinite(confidence) ? ` ${Math.round(confidence * 100)}%` : ""}`;
        ctx.strokeStyle = "#facc15";
        ctx.fillStyle = "rgba(15, 23, 42, 0.78)";
        ctx.strokeRect(x, y, w, h);
        const textWidth = ctx.measureText(label).width + 10;
        const textY = Math.max(18, y);
        ctx.fillRect(x, textY - 18, textWidth, 18);
        ctx.fillStyle = "#fef08a";
        ctx.fillText(label, x + 5, textY - 5);
      }
    }
    async function setYoloEnabled(enabled) {
      if (state.yoloControlBusy) return;
      if (enabled && !cameraViewers.front.active) {
        showOperationFeedback("请先打开前摄像头", "视频开始播放后才能启用 YOLO。", true);
        renderYoloWorkspace(state.latest || {});
        return;
      }
      state.yoloControlBusy = true;
      renderYoloWorkspace(state.latest || {});
      try {
        const payload = await api("POST", "/api/inspection/toggle", {enabled});
        showOperationFeedback(enabled ? "YOLO 已启用" : "YOLO 已关闭", payload.message || payload);
        mergeInspectionState(await fetchJson("/api/inspection/state"));
      } catch (err) {
        showOperationFeedback(enabled ? "YOLO 启用失败" : "YOLO 关闭失败", err, true);
      } finally {
        state.yoloControlBusy = false;
        renderYoloWorkspace(state.latest || {});
      }
    }
    function renderYoloWorkspace(snapshot) {
      const statusBox = $("yoloStatus");
      const resultBox = $("detections");
      if (!statusBox || !resultBox) return;
      const status = topicPayload(snapshot && snapshot.inspection_status) || {};
      const control = snapshot && snapshot.inspection_control || {};
      const detectionPayload = topicPayload(snapshot && snapshot.detections) || {};
      const enabled = status.enabled === true || control.enabled === true;
      const rows = enabled && Array.isArray(detectionPayload.detections)
        ? detectionPayload.detections
        : (enabled && Array.isArray(detectionPayload) ? detectionPayload : []);
      const ready = status.ready === true;
      const backend = status.backend || detectionPayload.backend || "未接入";
      const inferenceMs = Number(status.last_inference_ms);
      const frameAge = Number(status.last_frame_age_s);
      resultBox.hidden = !enabled;
      const toggle = $("yoloEnabledToggle");
      const toggleLabel = $("yoloToggleLabel");
      if (toggle) {
        toggle.checked = enabled;
        toggle.disabled = state.yoloControlBusy || control.available !== true || !cameraViewers.front.active;
      }
      if (toggleLabel) {
        toggleLabel.textContent = state.yoloControlBusy
          ? (enabled ? "关闭中" : "启动中")
          : (!cameraViewers.front.active ? "先开视频" : (control.available !== true ? "未接入" : (enabled ? "已启用" : "已关闭")));
      }
      statusBox.textContent = [
        !enabled ? "YOLO 已关闭" : (ready ? "YOLO 已就绪" : "YOLO 启动中"),
        `后端 ${backend}`,
        enabled && Number.isFinite(inferenceMs) ? `推理 ${fmtNumber(inferenceMs, 1)}ms` : "",
        enabled && Number.isFinite(frameAge) ? `画面 ${fmtAge(frameAge)}前` : "",
        status.last_error ? `异常 ${status.last_error}` : ""
      ].filter(Boolean).join(" / ");
      statusBox.classList.toggle("fail", Boolean(status.last_error) || (enabled && status.ready === false));
      drawYoloOverlay(snapshot);
      resultBox.innerHTML = "";
      if (!rows.length) {
        if (enabled) {
          resultBox.innerHTML = `<div class="small">${ready ? "当前画面没有检测目标" : "等待 YOLO 检测结果"}</div>`;
        }
        return;
      }
      for (const item of rows.slice(0, 50)) {
        const confidence = Number(item.confidence);
        const bbox = Array.isArray(item.bbox_xyxy) ? item.bbox_xyxy : [];
        const row = document.createElement("div");
        row.className = "detection-row";
        row.innerHTML = `
          <div><div class="detection-name">${escapeHtml(item.class_name || `类别 ${item.class_id ?? "-"}`)}</div><div class="detection-meta">${escapeHtml(bbox.length === 4 ? `区域 ${bbox.map(value => fmtNumber(Number(value), 0)).join(", ")}` : `摄像头 ${detectionPayload.camera || status.camera || "-"}`)}</div></div>
          <div class="detection-confidence">${Number.isFinite(confidence) ? `${fmtNumber(confidence * 100, 1)}%` : "-"}</div>`;
        resultBox.appendChild(row);
      }
    }
    function floorSwitchTransactionText(transaction) {
      const stateName = String((transaction && transaction.state) || "").toUpperCase();
      if (stateName === "SWITCHING_MAP") return "正在切换目标地图";
      if (stateName === "RELOCALIZING") return "正在目标层重定位";
      if (stateName === "COMMITTED") return "跨楼层切换完成";
      if (stateName === "FAILED") return "跨楼层切换失败，任务已停止";
      return "";
    }
    function renderTaskExecutionFlow(activeTask, waypoint, transaction = null) {
      const box = $("taskExecutionFlow");
      if (!box) return;
      const transactionState = String((transaction && transaction.state) || "").toUpperCase();
      const activeTransaction = ["SWITCHING_MAP", "RELOCALIZING"].includes(transactionState);
      const transactionMatchesTask = Boolean(
        activeTask
        && String((transaction && transaction.task_id) || "")
        && String(transaction.task_id) === String(activeTask.task_id || "")
      );
      const showTransaction = activeTransaction || (
        ["COMMITTED", "FAILED"].includes(transactionState) && transactionMatchesTask
      );
      const transactionText = showTransaction ? floorSwitchTransactionText(transaction) : "";
      const transactionHtml = transactionText
        ? `<div class="task-transaction ${transactionState === "FAILED" ? "fail" : (transactionState === "COMMITTED" ? "ok" : "warn")}"><strong>${escapeHtml(transactionText)}</strong><span>${escapeHtml((transaction && transaction.message) || "")}</span></div>`
        : "";
      if (!activeTask || activeTask.status !== "running") {
        box.innerHTML = transactionHtml || '<div class="small">暂无执行任务</div>';
        return;
      }
      const task = state.tasks.find(item => String(item.id || "") === String(activeTask.task_id || ""));
      const waypoints = task && Array.isArray(task.waypoints)
        ? task.waypoints
        : (Array.isArray(activeTask.annotation_ids)
          ? activeTask.annotation_ids.map(id => state.annotations.find(item => String(item.id || "") === String(id)) || {id})
          : []);
      const total = Math.max(waypoints.length, Array.isArray(activeTask.annotation_ids) ? activeTask.annotation_ids.length : 0);
      const current = Math.max(0, Math.min(Math.max(0, total - 1), Number(activeTask.index) || 0));
      const phaseText = taskPhaseText(activeTask, waypoint);
      const progress = total ? Math.max(0, Math.min(100, current / total * 100)) : 0;
      const rows = waypoints.map((item, index) => {
        const label = item && (item.label || item.id) || `点位 ${index + 1}`;
        const floor = item && item.floor ? ` / ${item.floor}` : "";
        const stateClass = index < current ? "done" : (index === current ? "active" : "pending");
        const stateText = index < current ? "已完成" : (index === current ? phaseText : "等待");
        return `<div class="task-flow-row ${stateClass}"><span class="task-flow-index">${index + 1}</span><span>${escapeHtml(label + floor)}</span><span class="task-flow-state">${stateText}</span></div>`;
      }).join("");
      box.innerHTML = `${transactionHtml}
        <div class="task-flow-head"><strong>${escapeHtml(activeTask.task_name || activeTask.task_id || "执行任务")}</strong><span>${total ? `${current + 1} / ${total}` : phaseText}</span></div>
        <div class="task-progress-track"><div class="task-progress-fill" style="width:${progress}%"></div></div>
        <div class="task-flow-list">${rows || `<div class="small">${escapeHtml(activeTask.status_message || phaseText)}</div>`}</div>`;
    }
    async function loadPreflight() {
      try {
        const payload = await fetchJson("/api/preflight");
        const result = payload.preflight || null;
        renderPreflight(result);
        return result;
      } catch (err) {
        renderPreflight({
          ok: false,
          running: false,
          failures: 1,
          warnings: 0,
          summary: "无法读取自检结果，请检查前端与服务连接",
          age_sec: 0,
          items: [{key: "preflight_fetch", label: "自检结果读取", status: "fail", message: err.message || "请求失败"}]
        });
        return null;
      }
    }
    async function pollPreflightUntilDone(maxMs = 90000) {
      const deadline = Date.now() + maxMs;
      let result = null;
      while (Date.now() < deadline) {
        await sleepMs(1500);
        result = await loadPreflight();
        if (result && !result.running) return result;
      }
      throw {ok: false, message: "后台自检仍在执行，请刷新自检结果或查看 m20pro-real.service 日志"};
    }
    async function runPreflight() {
      const buttons = [$("runPreflightBtn"), $("taskRunPreflightBtn")].filter(Boolean);
      for (const btn of buttons) btn.disabled = true;
      renderPreflight({
        ...(state.preflight || {}),
        ok: false,
        running: true,
        summary: "基础自检中（工位/未重定位时只确认基础链路），请稍候",
        age_sec: 0
      });
      if ($("taskPreflightSummary")) $("taskPreflightSummary").textContent = "基础自检中（工位/未重定位时只确认基础链路）...";
      try {
        const payload = await apiWithTimeout("POST", "/api/preflight/run", {mode: "move", site: "auto", wait: false}, 10000);
        const result = payload.preflight || payload;
        renderPreflight(result);
        if (payload.running || (result && result.running)) await pollPreflightUntilDone();
        await loadTasks();
      } catch (err) {
        renderPreflight({
          ok: false,
          navigation_ready: false,
          summary: err.message || "自检请求失败",
          age_sec: 0,
          items: [{
            key: "preflight_request",
            label: "自检请求",
            status: "fail",
            message: err.message || JSON.stringify(err)
          }]
        });
        setLog("preflightRaw", err);
      } finally {
        for (const btn of buttons) btn.disabled = false;
      }
    }
    function effectiveCurrentMapId() {
      return state.selectedMapId || state.effectiveMapId || state.workingMapId || "";
    }
    function renderRecordingStatus(payload) {
      const box = $("recordingStatus");
      if (!box) return;
      const recording = payload && payload.recording ? payload.recording : {};
      const lines = [];
      lines.push(recording.running ? "正在录包" : (recording.completed ? "录包已完成" : "未录包"));
      if (recording.prefix) lines.push(`名称 ${recording.prefix}`);
      if (recording.started_at) lines.push(`开始 ${recording.started_at}`);
      if (recording.bag_path) lines.push(`路径 ${recording.bag_path}`);
      if (recording.return_code !== undefined) lines.push(`返回码 ${recording.return_code}`);
      box.textContent = lines.join(" / ");
      if ($("recordingTopStatus")) {
        $("recordingTopStatus").textContent = recording.running
          ? "录制中"
          : (recording.completed ? "已完成" : "未录制");
      }
      $("startRecordingBtn").disabled = !!recording.running;
      $("stopRecordingBtn").disabled = !recording.running;
    }
    function formatRecordingBytes(value) {
      const bytes = Number(value);
      if (!Number.isFinite(bytes) || bytes < 0) return "大小未知";
      if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
      if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
      return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`;
    }
    function formatRecordingDuration(value) {
      const seconds = Number(value);
      if (!Number.isFinite(seconds) || seconds < 0) return "时长未知";
      if (seconds < 60) return `${seconds.toFixed(0)}s`;
      return `${Math.floor(seconds / 60)}分${Math.round(seconds % 60)}s`;
    }
    function renderRecordingList(payload) {
      const box = $("recordingList");
      if (!box) return;
      const recordings = payload && Array.isArray(payload.recordings) ? payload.recordings : [];
      if (!recordings.length) {
        box.innerHTML = '<div class="small">暂无已保存录包</div>';
        return;
      }
      box.innerHTML = recordings.map(item => {
        const id = escapeHtml(item.id || "");
        const name = escapeHtml(item.name || item.id || "未命名录包");
        const metadata = [
          formatRecordingBytes(item.size_bytes),
          item.duration_s === null || item.duration_s === undefined ? "时长未知" : formatRecordingDuration(item.duration_s),
          item.message_count === null || item.message_count === undefined ? "消息数未知" : `${item.message_count} 条消息`,
          item.modified_at || "时间未知"
        ].join(" / ");
        return `<article class="recording-item">
          <div class="recording-item-head"><strong class="recording-item-name" title="${name}">${name}</strong></div>
          <div class="recording-item-meta">${escapeHtml(metadata)}</div>
          <div class="recording-item-actions">
            <button type="button" data-recording-download="${id}" title="下载此录包">下载</button>
            <button type="button" data-recording-rename="${id}">改名</button>
            <button type="button" class="danger" data-recording-delete="${id}">删除</button>
          </div>
        </article>`;
      }).join("");
      box.querySelectorAll("[data-recording-download]").forEach(button => {
        button.addEventListener("click", () => {
          const id = button.dataset.recordingDownload || "";
          window.location.href = `/api/recording/download?id=${encodeURIComponent(id)}`;
        });
      });
      box.querySelectorAll("[data-recording-rename]").forEach(button => {
        button.addEventListener("click", async () => {
          const id = button.dataset.recordingRename || "";
          const current = recordings.find(item => String(item.id) === id);
          const name = window.prompt("输入新的录包名称", current ? current.name : id);
          if (name === null) return;
          button.disabled = true;
          try {
            await api("POST", "/api/recording/rename", {id, name});
            await loadRecordingList();
          } catch (err) {
            showOperationFeedback("录包改名失败", err, true);
          } finally {
            button.disabled = false;
          }
        });
      });
      box.querySelectorAll("[data-recording-delete]").forEach(button => {
        button.addEventListener("click", async () => {
          const id = button.dataset.recordingDelete || "";
          const current = recordings.find(item => String(item.id) === id);
          if (!window.confirm(`确认删除录包“${current ? current.name : id}”？此操作不可恢复。`)) return;
          button.disabled = true;
          try {
            await api("DELETE", `/api/recording?id=${encodeURIComponent(id)}`);
            await loadRecordingList();
          } catch (err) {
            showOperationFeedback("删除录包失败", err, true);
          } finally {
            button.disabled = false;
          }
        });
      });
    }
    async function loadRecordingList() {
      const payload = await fetchJson("/api/recording/list");
      renderRecordingList(payload);
      return payload;
    }
    async function loadRecordingStatus() {
      if (!$("recordingStatus")) return;
      const payload = await fetchJson("/api/recording/status");
      state.lastRecordingRefreshAt = Date.now();
      renderRecordingStatus(payload);
    }
    function currentAnnotationMapId() {
      return effectiveCurrentMapId() || "live_map";
    }
    function asNumber(id, fallback) {
      const value = Number($(id).value);
      return Number.isFinite(value) ? value : fallback;
    }
    function asInteger(id, fallback) {
      const value = Number.parseInt($(id).value, 10);
      return Number.isFinite(value) ? value : fallback;
    }
    function annotationManualType(item) {
      return item.manual_point_type || manualTypeByUiType[item.type] || "task";
    }
    function annotationTypeLabel(item) {
      const manualType = annotationManualType(item);
      if (item && ["stair_entry", "stair_exit", "stair_switch"].includes(item.type)) {
        return typeNames[item.type];
      }
      return manualPointTypeNames[manualType] || typeNames[item.type] || manualType || "点位";
    }
    function annotationTypeColor(item) {
      if (item && typeColors[item.type]) return typeColors[item.type];
      const manualType = annotationManualType(item);
      return manualPointTypeColors[manualType] || typeColors[item.type] || "#0f6bff";
    }
    function syncPointDefaults(force) {
      const uiType = $("markType").value;
      const manualType = manualTypeByUiType[uiType] || "task";
      const defaults = defaultByManualType[manualType] || defaultByManualType.task;
      if (force || !$("markDwell").value.trim()) $("markDwell").value = String(defaults.dwell);
      const gait = defaultGaitByUiType[uiType] || defaults.gait;
      if (force || !$("markGait").value.trim()) $("markGait").value = String(gait);
      if (force || !$("markSpeed").value.trim()) $("markSpeed").value = String(defaults.speed);
    }
    async function fetchJson(url, init) {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 15000);
      try {
        const res = await fetch(url, { cache: "no-store", signal: controller.signal, ...(init || {}) });
        const payload = await res.json();
        if (!res.ok || payload.ok === false) throw payload;
        return payload;
      } catch (err) {
        if (err && err.name === "AbortError") {
          throw {ok: false, message: "请求超时：15 秒内未收到网页返回；请刷新页面或检查 m20pro-real.service"};
        }
        throw err;
      } finally {
        clearTimeout(timer);
      }
    }
    async function api(method, url, body) {
      const res = await fetch(url, {
        method,
        headers: {"Content-Type": "application/json"},
        body: body === undefined ? undefined : JSON.stringify(body)
      });
      const payload = await res.json();
      if (!res.ok || payload.ok === false) throw payload;
      return payload;
    }
    async function apiWithTimeout(method, url, body, timeoutMs) {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), timeoutMs);
      try {
        const res = await fetch(url, {
          method,
          headers: {"Content-Type": "application/json"},
          body: body === undefined ? undefined : JSON.stringify(body),
          signal: controller.signal
        });
        const payload = await res.json();
        if (!res.ok || payload.ok === false) throw payload;
        return payload;
      } catch (err) {
        if (err && err.name === "AbortError") {
          throw {ok: false, message: `请求超时：${Math.round(timeoutMs / 1000)} 秒内未收到网页返回；请刷新自检结果或检查 m20pro-real.service`};
        }
        throw err;
      } finally {
        clearTimeout(timer);
      }
    }
    async function apiMaybeManual(method, url, body) {
      const res = await fetch(url, {
        method,
        headers: {"Content-Type": "application/json"},
        body: body === undefined ? undefined : JSON.stringify(body)
      });
      const payload = await res.json();
      if (payload && payload.manual_required) return payload;
      if (!res.ok || payload.ok === false) throw payload;
      return payload;
    }
    function splitDddmrPathList(value) {
      const values = Array.isArray(value)
        ? value
        : String(value || "").replace(/\r/g, "\n").split(/[\n,]/);
      const result = [];
      for (const item of values) {
        const textValue = String(item || "").trim();
        if (textValue && !result.includes(textValue)) result.push(textValue);
      }
      return result;
    }
    function dddmrAssetFormPayload() {
      const floor = String($("dddmrAssetFloor").value || "").trim();
      const label = String($("dddmrAssetLabel").value || "").trim();
      const note = String($("dddmrAssetNote").value || "").trim();
      const mapcloud = splitDddmrPathList($("dddmrAssetMapcloud").value);
      const mapground = splitDddmrPathList($("dddmrAssetMapground").value);
      return {
        floor,
        label,
        note,
        mapcloud,
        mapground,
        source: "web_dashboard",
      };
    }
    function dddmrMapDirectoryFromRecord(record) {
      const direct = String(record && (record.directory || record.map_dir || "")).trim();
      if (direct) return direct.replace(/[\\/]+$/, "");
      const yamlPath = String(record && (record.yaml_path || record.map_yaml || record.map_path || "")).trim();
      if (!yamlPath) return "";
      return yamlPath.replace(/\\/g, "/").replace(/\/[^/]+$/, "");
    }
    function dddmrDefaultAssetPathFromRecord(record) {
      const directory = dddmrMapDirectoryFromRecord(record);
      return directory ? `${directory}/full_cloud.pcd` : "";
    }
    function fillDddmrAssetDraftFromCurrentMap() {
      const record = mapRecordById(state.selectedMapId) || mapRecordById(state.effectiveMapId) || mapRecordById(state.workingMapId);
      if (!record) {
        setDddmrAssetFeedback("请先选择一个地图，再自动填充资产。", "fail");
        return;
      }
      const cloudPath = dddmrDefaultAssetPathFromRecord(record);
      if (!cloudPath) {
        setDddmrAssetFeedback("当前地图没有可推导的 yaml_path / directory，无法自动填充。", "fail");
        return;
      }
      const floor = String(record.floor || displayedMapFloor() || "").trim();
      const label = String(record.name || record.label || record.id || floor || "").trim();
      const note = `自动填充自 ${record.name || record.id || "当前地图"} 的 full_cloud.pcd，用于最小通路验证`;
      setDddmrAssetDraft({
        floor,
        label,
        note,
        mapcloud: [cloudPath],
        mapground: [cloudPath],
        source: "current_map_directory"
      });
      setDddmrAssetFeedback(`已从当前地图目录填入候选 ${cloudPath}；如有正式地面地图，请再替换。`, "ok");
    }
    function dddmrAssetRecordForFloor(workspace, floor) {
      const floors = workspace && Array.isArray(workspace.floors) ? workspace.floors : [];
      const needle = String(floor || "").trim();
      return floors.find(item => String(item.floor || "").trim() === needle) || null;
    }
    function activeDddmrAssetRecord(payload = state.latest, map3d = null) {
      const assets = state.dddmrMapAssets || dddmrMapAssetsPayload(payload);
      const workspace = assets && assets.workspace && typeof assets.workspace === "object" ? assets.workspace : {};
      const status = assets && assets.status && typeof assets.status === "object" ? assets.status : {};
      const floors = Array.isArray(workspace.floors) ? workspace.floors : [];
      const targetFloor = String(
        (map3d && map3d.floor)
        || status.floor
        || currentRobotFloor(payload)
        || displayedMapFloor()
        || ""
      ).trim();
      return dddmrAssetRecordForFloor(workspace, targetFloor)
        || floors.find(item => item && item.ready)
        || null;
    }
    function dddmrAssetDisplayLabel(record, fallbackFloor = "") {
      if (!record) return "";
      const label = String(record.label || "").trim();
      const floor = String(record.floor || fallbackFloor || "").trim();
      if (label && label !== floor) return label;
      return floor;
    }
    function spatialMapDisplayTitle(map = state.spatialMap) {
      if (!map) return "等待地图";
      const label = dddmrAssetDisplayLabel(map.assetRecord, map.floor);
      return label ? `3D地图：${label}` : "当前3D地图";
    }
    function spatialMapDisplayMeta(map = state.spatialMap) {
      if (!map) return "";
      return text(map.floor || "");
    }
    function updateLiveSpatialMapHeader() {
      $("mapTitle").textContent = spatialMapDisplayTitle();
      $("mapMeta").textContent = spatialMapDisplayMeta();
    }
    function setDddmrAssetDraft(record) {
      const payload = record || null;
      state.dddmrAssetDraft = payload ? {
        ...payload,
        mapcloud: Array.isArray(payload.mapcloud) ? payload.mapcloud.slice() : splitDddmrPathList(payload.mapcloud),
        mapground: Array.isArray(payload.mapground) ? payload.mapground.slice() : splitDddmrPathList(payload.mapground)
      } : null;
      $("dddmrAssetFloor").value = payload && payload.floor ? String(payload.floor) : "";
      $("dddmrAssetLabel").value = payload && payload.label && payload.label !== payload.floor ? String(payload.label) : "";
      $("dddmrAssetNote").value = payload && payload.note ? String(payload.note) : "";
      $("dddmrAssetMapcloud").value = payload ? (Array.isArray(payload.mapcloud) ? payload.mapcloud.join("\n") : splitDddmrPathList(payload.mapcloud).join("\n")) : "";
      $("dddmrAssetMapground").value = payload ? (Array.isArray(payload.mapground) ? payload.mapground.join("\n") : splitDddmrPathList(payload.mapground).join("\n")) : "";
    }
    function dddmrMappingCommandText(mapping) {
      if (!mapping) return "start/finish/cancel: 未读取";
      const items = [
        ["start", mapping.start_configured],
        ["finish", mapping.finish_configured],
        ["cancel", mapping.cancel_configured],
      ];
      return items.map(([label, configured]) => `${label}:${configured ? "已配置" : "空"}`).join(" / ");
    }
    function dddmrMapAssetsTone(payload) {
      if (!payload) return "warn";
      if (payload.ok === false) return "fail";
      const workspace = payload.workspace || {};
      if (Number(workspace.ready_floor_count || 0) > 0) return "ok";
      if (payload.status && payload.status.ready) return "ok";
      return "warn";
    }
    function dddmrMapAssetsStatusLabel(payload) {
      if (!payload) return "等待";
      if (payload.ok === false) return "异常";
      const workspace = payload.workspace || {};
      const status = payload.status || {};
      if (status.ready && status.provisional) return "临时平面";
      const readyCount = Number(workspace.ready_floor_count || 0);
      if (readyCount > 0) return `就绪 ${readyCount}`;
      if (status.ready) return "就绪";
      return "待登记";
    }
    function dddmrMapAssetsSummaryText(payload) {
      if (!payload) return "等待资产清单和状态。";
      if (payload.ok === false) {
        return "资产清单读取失败。";
      }
      const workspace = payload.workspace || {};
      const status = payload.status || {};
      const floors = Number(workspace.floor_count || 0);
      const ready = Number(workspace.ready_floor_count || 0);
      const assets = Number(workspace.asset_count || floors || 0);
      const readyAssets = Number(workspace.ready_asset_count || ready || 0);
      const statusText = !status ? "无状态" : (status.ready
        ? `${status.provisional ? "临时平面" : "已就绪"}${status.floor ? ` / 楼层 ${text(status.floor)}` : ""}`
        : `${status.floor ? `楼层 ${text(status.floor)} / ` : ""}未就绪`);
      const manifest = payload.manifest_path ? "清单已配置" : "清单未配置";
      return `${manifest}；${readyAssets}/${assets} 张 3D 地图就绪；当前楼层 ${ready}/${floors}；状态 ${statusText}`;
    }
    function dddmrMapAssetsCurrentSummary(payload) {
      if (!payload || payload.ok === false) return "当前：未就绪";
      const workspace = payload.workspace && typeof payload.workspace === "object" ? payload.workspace : {};
      const floors = Array.isArray(workspace.floors) ? workspace.floors : [];
      const current = floors.find(item => item && item.active) || floors.find(item => item && item.ready) || null;
      if (!current) return "当前：未选择地图";
      const label = dddmrAssetDisplayLabel(current, current.floor);
      const floor = String(current.floor || "").trim();
      return `当前：${label || "未命名"}${floor ? ` · ${floor}` : ""}`;
    }
    function renderDddmrAssetWorkspace(box, workspace, assets) {
      if (!box) return;
      const floors = Array.isArray(workspace.floors) ? workspace.floors : [];
      const rows = Array.isArray(assets) && assets.length ? assets : floors;
      if (!rows.length) {
        box.innerHTML = '<div class="map-empty">暂无3D地图</div>';
        return;
      }
      box.innerHTML = rows.map(item => {
        const floor = String(item && item.floor ? item.floor : "");
        const assetId = String(item && item.asset_id ? item.asset_id : "");
        const ready = item && item.ready;
        const active = item && item.active;
        const label = text(item && item.label ? item.label : item && item.floor);
        const noteMeta = {};
        for (const part of String(item && item.note ? item.note : "").split(";")) {
          const eq = part.indexOf("=");
          if (eq > 0) noteMeta[part.slice(0, eq).trim()] = part.slice(eq + 1).trim();
        }
        return `
          <div class="map-asset-card${active ? " is-active" : ""}">
            <div class="map-asset-badge">3D</div>
            <div class="map-asset-main">
              <div class="map-asset-name">${escapeHtml(label || "未命名地图")}</div>
              <div class="map-asset-sub">
                ${floor ? `<span>${escapeHtml(floor)}</span>` : ""}
                ${noteMeta.project ? `<span>${escapeHtml(noteMeta.project)}</span>` : ""}
                ${noteMeta.building ? `<span>${escapeHtml(noteMeta.building)}</span>` : ""}
                ${active ? '<span class="tag ok">当前</span>' : ""}
                <span class="tag ${ready ? "ok" : "warn"}">${ready ? "就绪" : "未就绪"}</span>
              </div>
            </div>
            <div class="map-asset-actions">
              ${active ? "" : `<button type="button" data-dddmr-select-asset="${escapeHtml(assetId)}" ${!assetId ? "disabled" : ""}>设为当前</button>`}
              ${active ? `<button type="button" class="danger" data-dddmr-delete-floor="${escapeHtml(floor)}">取消当前</button>` : ""}
              <button type="button" class="danger" data-dddmr-delete-asset="${escapeHtml(assetId)}" data-dddmr-delete-label="${escapeHtml(label)}" data-dddmr-delete-active="${active ? "1" : "0"}" ${!assetId ? "disabled" : ""}>删除地图</button>
            </div>
          </div>`;
      }).join("");
      for (const button of box.querySelectorAll("[data-dddmr-select-asset]")) {
        button.addEventListener("click", async () => {
          const assetId = String(button.dataset.dddmrSelectAsset || "").trim();
          if (!assetId) return;
          if (!window.confirm("确认把这张 3D 地图设为当前楼层地图？")) return;
          button.disabled = true;
          try {
            const payload = await api("POST", "/api/dddmr/map_assets/select", {asset_id: assetId});
            state.dddmrMapAssets = payload.map_assets || payload;
            renderDddmrMapAssets(state.dddmrMapAssets);
            setDddmrAssetFeedback(payload.message || "已切换当前 3D 地图", "ok");
            await loadDddmrMapAssets(true).catch(console.warn);
          } catch (err) {
            setDddmrAssetFeedback(err && err.message ? err.message : "切换 3D 地图失败", "fail");
            showOperationFeedback("切换 3D 地图失败", err, true);
          } finally {
            button.disabled = false;
          }
        });
      }
      for (const button of box.querySelectorAll("[data-dddmr-delete-floor]")) {
        button.addEventListener("click", async () => {
          const floor = String(button.dataset.dddmrDeleteFloor || "").trim();
          if (!floor) return;
          if (!window.confirm(`确认取消楼层 ${floor} 的当前 3D 地图登记？\n\n这只会取消当前登记，不会删除地图文件。`)) return;
          button.disabled = true;
          try {
            const payload = await api("POST", "/api/dddmr/map_assets/delete", {floor});
            state.dddmrMapAssets = payload;
            renderDddmrMapAssets(payload);
            setDddmrAssetFeedback(payload.message || `已取消 ${floor} 的当前资产登记`, "ok");
          } catch (err) {
            setDddmrAssetFeedback(`取消 ${floor} 当前登记失败`, "fail");
            showOperationFeedback("取消资产登记失败", err, true);
          } finally {
            button.disabled = false;
          }
        });
      }
      for (const button of box.querySelectorAll("[data-dddmr-delete-asset]")) {
        button.addEventListener("click", async () => {
          const assetId = String(button.dataset.dddmrDeleteAsset || "").trim();
          const label = String(button.dataset.dddmrDeleteLabel || assetId || "").trim();
          const activeText = button.dataset.dddmrDeleteActive === "1"
            ? "\n\n注意：这是当前楼层正在登记的 3D 地图，删除会同时取消当前登记。"
            : "";
          if (!assetId) return;
          if (!window.confirm(`确认彻底删除 3D 地图“${label || assetId}”？\n\n会从 3D 地图列表删除该记录，并删除它独占的归档目录；此操作不可恢复。${activeText}`)) return;
          button.disabled = true;
          try {
            const payload = await api("POST", "/api/dddmr/map_assets/delete", {
              asset_id: assetId,
              delete_files: true
            });
            state.dddmrMapAssets = payload;
            renderDddmrMapAssets(payload);
            const fileText = payload.files_deleted ? "，归档文件已删除" : "";
            setDddmrAssetFeedback(payload.message ? `${payload.message}${fileText}` : `已删除 ${label || assetId}${fileText}`, "ok");
            await loadDddmrMapAssets(true).catch(console.warn);
          } catch (err) {
            setDddmrAssetFeedback(`删除 ${label || assetId} 失败`, "fail");
            showOperationFeedback("删除 3D 地图失败", err, true);
          } finally {
            button.disabled = false;
          }
        });
      }
    }
    function renderDddmrMapAssets(payload = state.dddmrMapAssets) {
      const data = payload && typeof payload === "object" ? payload : null;
      const workspace = data && data.workspace && typeof data.workspace === "object" ? data.workspace : {floor_count: 0, ready_floor_count: 0, floors: []};
      const mapping = data && data.mapping && typeof data.mapping === "object" ? data.mapping : null;
      const status = data && data.status && typeof data.status === "object" ? data.status : null;
      for (const id of ["dddmrMapAssetsStatus", "mapDddmrMapAssetsStatus"]) {
        const statusTag = $(id);
        if (statusTag) {
          statusTag.textContent = dddmrMapAssetsStatusLabel(data);
          statusTag.className = `tag ${dddmrMapAssetsTone(data)}`;
        }
      }
      const summary = $("dddmrMapAssetsSummary");
      if (summary) summary.textContent = dddmrMapAssetsSummaryText(data);
      const popoverSummary = $("mapStatusDetail");
      if (popoverSummary) popoverSummary.textContent = dddmrMapAssetsCurrentSummary(data);
      const manifestPath = $("dddmrMapAssetManifestPath");
      if (manifestPath) manifestPath.textContent = data && data.manifest_path ? "已配置" : "-";
      const statusText = $("dddmrMapAssetStatusText");
      if (statusText) {
        if (!status) statusText.textContent = "等待地图状态";
        else {
          const parts = [status.ready ? "已就绪" : "未就绪"];
          if (status.provisional) parts.push("临时平面");
          if (status.floor) parts.push(`楼层 ${text(status.floor)}`);
          if (Number.isFinite(Number(status.mapcloud_points)) || Number.isFinite(Number(status.mapground_points))) {
            parts.push(`点云 ${text(status.mapcloud_points || 0)} / 地面 ${text(status.mapground_points || 0)}`);
          }
          statusText.textContent = parts.join(" / ");
        }
      }
      const mappingHost = $("dddmrMapAssetMappingHost");
      if (mappingHost) {
        if (mapping) {
          mappingHost.textContent = `${text(mapping.host || "-")} / ${text(mapping.user || "-")}`;
        } else {
          mappingHost.textContent = "-";
        }
      }
      const commandStatus = $("dddmrMapAssetCommandStatus");
      if (commandStatus) commandStatus.textContent = dddmrMappingCommandText(mapping);
      if (state.spatialMap) {
        const backend = navigationBackendPayload(state.latest);
        state.spatialMap.assetRecord = activeDddmrAssetRecord(state.latest, backend.map_3d);
      }
      updateLiveSpatialMapHeader();
      renderDddmrAssetWorkspace($("dddmrAssetWorkspace"), workspace, workspace.assets || workspace.floors);
      renderDddmrAssetWorkspace($("mapDddmrAssetWorkspace"), workspace, workspace.assets || workspace.floors);
    }
    function setDddmrAssetFeedback(value, tone = "warn") {
      const box = $("dddmrAssetFeedback");
      if (!box) return;
      box.className = tone ? `compact-status ${tone}` : "compact-status";
      if (typeof value === "string") {
        box.textContent = value;
      } else {
        box.textContent = value ? JSON.stringify(value, null, 2) : "等待读取资产清单。";
      }
    }
    async function loadDddmrMapAssets(force = false) {
      if (state.loadingDddmrMapAssets) return state.dddmrMapAssets;
      const now = Date.now();
      if (!force && state.dddmrMapAssets && now - state.lastDddmrMapAssetsRefreshAt < 3000) {
        return state.dddmrMapAssets;
      }
      state.loadingDddmrMapAssets = true;
      try {
        const payload = await fetchJson("/api/dddmr/map_assets");
        state.dddmrMapAssets = payload;
        state.lastDddmrMapAssetsRefreshAt = Date.now();
        renderDddmrMapAssets(payload);
        return payload;
      } catch (err) {
        state.lastDddmrMapAssetsRefreshAt = Date.now();
        if (!state.dddmrMapAssets) renderDddmrMapAssets();
        setDddmrAssetFeedback(err && err.message ? err.message : "资产清单读取失败", "fail");
        throw err;
      } finally {
        state.loadingDddmrMapAssets = false;
      }
    }
    async function loadDddmrFieldTestAcceptance() {
      if (state.loadingDddmrFieldTest) return state.dddmrFieldTest;
      const button = $("refreshDddmrFieldTestBtn");
      const oldText = button ? button.textContent : "";
      state.loadingDddmrFieldTest = true;
      if (button) {
        button.disabled = true;
        button.textContent = "读取中...";
      }
      try {
        const payload = await fetchJson("/api/dddmr/field_test");
        state.dddmrFieldTest = payload;
        if (payload && payload.dddmr_field_test_mode) {
          state.dddmrFieldTestMode = payload.dddmr_field_test_mode;
        }
        if (payload && payload.dddmr_map_assets) {
          state.dddmrMapAssets = payload.dddmr_map_assets;
          renderDddmrMapAssets(state.dddmrMapAssets);
        }
        renderDddmrFieldTest(payload);
        return payload;
      } catch (err) {
        state.dddmrFieldTest = {
          ok: false,
          api: "/api/dddmr/field_test",
          field_test: {},
          acceptance: {
            ready: false,
            reason: "field_test_state_unavailable",
            blocked_by: ["web_state"]
          },
          next_steps: ["确认 104 Web 服务可访问"]
        };
        renderDddmrFieldTest(state.dddmrFieldTest);
        throw err;
      } finally {
        state.loadingDddmrFieldTest = false;
        if (button) {
          button.disabled = false;
          button.textContent = oldText || "读取状态";
        }
      }
    }
    function normalizedCanvasRect(rect) {
      return {
        left: Number(rect.left) || 0,
        top: Number(rect.top) || 0,
        width: Math.max(1, Number(rect.width) || 0),
        height: Math.max(1, Number(rect.height) || 0)
      };
    }
    function mapCanvasCssRect() {
      return normalizedCanvasRect(canvas.getBoundingClientRect());
    }
    function mapCanvasContainerRect() {
      const target = canvas.parentElement || canvas;
      return normalizedCanvasRect(target.getBoundingClientRect());
    }
    function mapCanvasDpr() {
      return Math.max(1, Number(window.devicePixelRatio) || 1);
    }
    function resetMapCanvasTransform(dpr = mapCanvasDpr()) {
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      return dpr;
    }
    function clearMapCanvasPixels() {
      ctx.save();
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.clearRect(0, 0, Math.max(1, canvas.width), Math.max(1, canvas.height));
      ctx.restore();
    }
    function syncMapCanvasBackingStore() {
      const targetRect = mapCanvasContainerRect();
      const widthStyle = `${targetRect.width}px`;
      const heightStyle = `${targetRect.height}px`;
      if (canvas.style.width !== widthStyle) canvas.style.width = widthStyle;
      if (canvas.style.height !== heightStyle) canvas.style.height = heightStyle;
      const dpr = mapCanvasDpr();
      const pixelWidth = Math.max(1, Math.round(targetRect.width * dpr));
      const pixelHeight = Math.max(1, Math.round(targetRect.height * dpr));
      if (canvas.width !== pixelWidth || canvas.height !== pixelHeight) {
        canvas.width = pixelWidth;
        canvas.height = pixelHeight;
      }
      clearMapCanvasPixels();
      resetMapCanvasTransform(dpr);
      const canvasRect = mapCanvasCssRect();
      return {
        left: canvasRect.left,
        top: canvasRect.top,
        width: targetRect.width,
        height: targetRect.height
      };
    }
    function resizeCanvas() {
      const before = getView();
      const rect = syncMapCanvasBackingStore();
      if (state.spatialMap && before && before.rect) {
        state.view.panX += (before.rect.width - rect.width) * 0.5;
        state.view.panY += (before.rect.height - rect.height) * 0.5;
        clampView();
      } else if (state.spatialMap) {
        state.view.panX = 0;
        state.view.panY = 0;
      }
      updateZoomReadout();
      draw();
    }
    function finiteSpatialSamples(value) {
      if (!Array.isArray(value)) return [];
      return value
        .filter(point => Array.isArray(point) && point.length >= 3)
        .map(point => point.slice(0, 3).map(Number))
        .filter(point => point.every(Number.isFinite));
    }
    function buildSpatialRenderModel(mapcloud, mapground, bounds) {
      const allPoints = mapcloud.concat(mapground);
      if (!allPoints.length) {
        return {
          cellSize: 0.1,
          cells: [],
          groundCells: [],
          cloudCells: [],
          maxCellCount: 0
        };
      }
      const span = Math.max(bounds.maxX - bounds.minX, bounds.maxY - bounds.minY, 1.0);
      const targetCellsAcross = Math.max(42, Math.min(140, Math.round(Math.sqrt(allPoints.length) * 2.2)));
      // Density floor: a render cell smaller than the mean sample spacing
      // leaves holes on large maps (2026-08-31: whole-floor looked sparse
      // next to a small dense map under the same sample budget).
      const densityFloor = Math.sqrt(
        Math.max(0.0, (bounds.maxX - bounds.minX) * (bounds.maxY - bounds.minY))
        / Math.max(1, allPoints.length)
      );
      const cellSize = Math.max(0.04, Math.min(0.45, span / targetCellsAcross, densityFloor * 1.15));
      const buckets = new Map();
      const addPoint = (point, layer) => {
        const x = Number(point[0]);
        const y = Number(point[1]);
        const z = Number(point[2]);
        if (![x, y, z].every(Number.isFinite)) return;
        const ix = Math.floor((x - bounds.minX) / cellSize);
        const iy = Math.floor((y - bounds.minY) / cellSize);
        const key = `${ix}:${iy}`;
        let cell = buckets.get(key);
        if (!cell) {
          cell = {
            ix,
            iy,
            x: 0,
            y: 0,
            z: 0,
            topZ: z,
            baseZ: z,
            minZ: z,
            maxZ: z,
            count: 0,
            groundHits: 0,
            cloudHits: 0
          };
          buckets.set(key, cell);
        }
        cell.count += 1;
        cell.x += x;
        cell.y += y;
        cell.z += z;
        cell.minZ = Math.min(cell.minZ, z);
        cell.maxZ = Math.max(cell.maxZ, z);
        if (layer === "ground") {
          cell.groundHits += 1;
          cell.baseZ = cell.groundHits === 1
            ? z
            : (cell.baseZ * (cell.groundHits - 1) + z) / cell.groundHits;
        } else {
          cell.cloudHits += 1;
          cell.topZ = Math.max(cell.topZ, z);
        }
      };
      for (const point of mapground) addPoint(point, "ground");
      for (const point of mapcloud) addPoint(point, "cloud");
      const cells = Array.from(buckets.values()).map(cell => {
        const count = Math.max(1, cell.count);
        return {
          ...cell,
          x: cell.x / count,
          y: cell.y / count,
          z: cell.z / count,
          topZ: cell.cloudHits > 0 ? cell.topZ : cell.maxZ,
          baseZ: cell.groundHits > 0 ? cell.baseZ : cell.minZ
        };
      });
      const maxCellCount = cells.reduce((maxValue, cell) => Math.max(maxValue, cell.count), 0);
      for (const cell of cells) {
        cell.density = maxCellCount > 0 ? Math.log1p(cell.count) / Math.log1p(maxCellCount) : 0;
        cell.hasCloud = cell.cloudHits > 0;
        cell.hasGround = cell.groundHits > 0;
      }
      return {
        cellSize,
        cells,
        groundCells: cells.filter(cell => cell.hasGround),
        cloudCells: cells.filter(cell => cell.hasCloud),
        maxCellCount
      };
    }
    // 2026-09-01: height-slice topdown + cloud picking for spatial marks.
    // Multi-level maps (stairs/atriums) used to collapse every floor into one
    // (x,y) overlay that read like a side view, and clicks always produced
    // Z=0.  Now the topdown renders a single height band and clicks sample Z
    // from the standing surface of the visible layer.
    function computeHeightLayers(renderModel) {
      const cells = (renderModel && renderModel.cells) || [];
      const grounds = cells
        .filter(cell => cell.hasGround)
        .map(cell => Number(cell.baseZ))
        .filter(Number.isFinite)
        .sort((a, b) => a - b);
      if (!grounds.length) return [];
      const layers = [];
      let prev = grounds[0];
      let count = 1;
      let sum = grounds[0];
      for (let i = 1; i < grounds.length; i += 1) {
        const z = grounds[i];
        if (z - prev > 0.5) {
          layers.push({z: sum / count, count});
          count = 0;
          sum = 0;
        }
        count += 1;
        sum += z;
        prev = z;
      }
      layers.push({z: sum / count, count});
      return layers.sort((a, b) => b.count - a.count);
    }
    function defaultSliceZ(map) {
      const layers = Array.isArray(map.layers) ? map.layers : [];
      if (layers.length) return layers[0].z;
      return (Number(map.minZ) + Number(map.maxZ)) / 2;
    }
    function effectiveSliceZ(map) {
      const value = Number(state.view.sliceZ);
      if (Number.isFinite(value)) {
        return Math.max(Number(map.minZ) - 0.5, Math.min(Number(map.maxZ) + 0.5, value));
      }
      return defaultSliceZ(map);
    }
    function sliceWindow(map) {
      const z = effectiveSliceZ(map);
      return [z - 0.25, z + 1.2];
    }
    async function pickStandingZ(x, y, hint) {
      try {
        const payload = await fetchJson("/api/3d/pick", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({x, y, z_hint: Number.isFinite(hint) ? hint : 0, radius: 0.45})
        });
        if (payload && payload.ok && Number.isFinite(Number(payload.z))) return Number(payload.z);
      } catch (err) {
        console.warn("server pick failed, fallback to sampled cell", err);
      }
      const cell = pickTopdownCell(x, y);
      return cell ? (cell.hasGround ? cell.baseZ : cell.minZ) : null;
    }
    function pickTopdownCell(x, y) {
      const map = state.spatialMap;
      if (!map) return null;
      const cells = ((map.renderModel || {}).cells) || [];
      const [lo, hi] = sliceWindow(map);
      let best = null;
      let bestDist = Infinity;
      for (const cell of cells) {
        if (cell.baseZ > hi || cell.topZ < lo) continue;
        const dx = cell.x - x;
        const dy = cell.y - y;
        const dist = dx * dx + dy * dy;
        if (dist < bestDist) {
          bestDist = dist;
          best = cell;
        }
      }
      return best;
    }
    function pick3dMarkPoint(clientX, clientY) {
      const map = state.spatialMap;
      if (!map) return null;
      const view = get3dView();
      const cx = clientX - view.rect.left;
      const cy = clientY - view.rect.top;
      let best = null;
      let bestDist = 14 * 14;
      const consider = (point) => {
        const projected = projectSpatial3d(point, view);
        if (!projected) return;
        const dx = projected.x - cx;
        const dy = projected.y - cy;
        const dist = dx * dx + dy * dy;
        if (dist < bestDist) {
          bestDist = dist;
          best = point;
        }
      };
      for (const point of (map.mapcloud || [])) consider(point);
      for (const point of (map.mapground || [])) consider(point);
      return best;
    }
    function updateSliceBar() {
      const bar = $("sliceBar");
      if (!bar) return;
      const map = state.spatialMap;
      const show = Boolean(map) && effectiveMapViewMode() === "topdown";
      bar.style.display = show ? "flex" : "none";
      if (!show || !map) return;
      const slider = $("sliceZSlider");
      if (slider) {
        slider.min = (Number(map.minZ) - 0.3).toFixed(2);
        slider.max = (Number(map.maxZ) + 0.3).toFixed(2);
        slider.step = "0.05";
        const z = effectiveSliceZ(map);
        if (document.activeElement !== slider) slider.value = z.toFixed(2);
      }
      const readout = $("sliceZReadout");
      if (readout) readout.textContent = `层高 ${effectiveSliceZ(map).toFixed(2)} m`;
      const layers = Array.isArray(map.layers) ? map.layers : [];
      const z = effectiveSliceZ(map);
      const up = $("sliceUpBtn");
      const down = $("sliceDownBtn");
      const floors = Array.isArray(state.floors) ? state.floors : [];
      const upList = floors.length ? floors : layers;
      if (up) up.disabled = !upList.some(layer => layer.z > z + 0.2);
      if (down) down.disabled = !upList.some(layer => layer.z < z - 0.2);
      const tabs = $("floorTabs");
      if (tabs) {
        if (floors.length > 1) {
          tabs.innerHTML = "";
          for (const floor of floors) {
            const btn = document.createElement("button");
            btn.type = "button";
            btn.textContent = floor.name;
            btn.title = `地面 z≈${floor.z} m（${floor.ground_points} 点）`;
            if (Math.abs(z - floor.z) < 0.3) btn.classList.add("active-floor");
            btn.addEventListener("click", () => {
              state.view.sliceZ = floor.z;
              draw();
            });
            tabs.appendChild(btn);
          }
          tabs.style.display = "flex";
        } else {
          tabs.style.display = "none";
          tabs.innerHTML = "";
        }
      }
    }
    function buildSpatialMap(payload) {
      const backend = navigationBackendPayload(payload);
      const map3d = backend && backend.map_3d && typeof backend.map_3d === "object"
        ? backend.map_3d
        : {};
      const assetRecord = activeDddmrAssetRecord(payload, map3d);
      const mapcloud = finiteSpatialSamples(map3d.mapcloud_samples);
      const mapground = finiteSpatialSamples(map3d.mapground_samples);
      const points = mapcloud.concat(mapground);
      if (!points.length) return null;
      const xs = points.map(point => point[0]);
      const ys = points.map(point => point[1]);
      const zs = points.map(point => point[2]);
      const rawMinX = Math.min(...xs);
      const rawMaxX = Math.max(...xs);
      const rawMinY = Math.min(...ys);
      const rawMaxY = Math.max(...ys);
      const span = Math.max(rawMaxX - rawMinX, rawMaxY - rawMinY, 1.0);
      const padding = Math.max(0.5, Math.min(2.0, span * 0.05));
      const minX = rawMinX - padding;
      const maxX = rawMaxX + padding;
      const minY = rawMinY - padding;
      const maxY = rawMaxY + padding;
      const resolution = Math.max(0.02, Math.max(maxX - minX, maxY - minY) / 1600);
      const bounds = {minX, maxX, minY, maxY};
      const renderModel = buildSpatialRenderModel(mapcloud, mapground, bounds);
      const layers = computeHeightLayers(renderModel);
      const signature = [
        currentRobotFloor(payload),
        mapcloud.length,
        mapground.length,
        dddmrAssetDisplayLabel(assetRecord, currentRobotFloor(payload)),
        minX.toFixed(2),
        maxX.toFixed(2),
        minY.toFixed(2),
        maxY.toFixed(2)
      ].join(":");
      return {
        floor: map3d.floor || currentRobotFloor(payload),
        frameId: map3d.mapcloud_frame || map3d.mapground_frame || "map",
        assetRecord,
        mapcloud,
        mapground,
        minZ: Math.min(...zs),
        maxZ: Math.max(...zs),
        resolution,
        width: (maxX - minX) / resolution,
        height: (maxY - minY) / resolution,
        origin: {x: minX, y: minY},
        bounds,
        renderModel,
        layers,
        signature
      };
    }
    function spatialMapIdentity(payload, map3d, assetRecord) {
      return [
        currentRobotFloor(payload),
        Number((map3d || {}).mapcloud_points || 0),
        Number((map3d || {}).mapground_points || 0),
        dddmrAssetDisplayLabel(assetRecord, currentRobotFloor(payload))
      ].join(":");
    }
    async function loadSpatialMapSamples() {
      if (state.loadingSpatialMap) return;
      state.loadingSpatialMap = true;
      try {
        const payload = await fetchJson("/api/3d/spatial_map");
        const base = state.latest || {};
        const wrapped = {
          ...base,
          navigation_backend: {
            ...(base.navigation_backend || {}),
            map_3d: payload && payload.map_3d
          }
        };
        const next = buildSpatialMap(wrapped);
        if (next) {
          const previousSignature = state.spatialMap && state.spatialMap.signature;
          state.spatialMap = next;
          if (next.signature !== previousSignature) {
            resetMapView(false);
            loadFloors().catch(console.warn);
          }
          if (!state.selectedMapId) {
            updateLiveSpatialMapHeader();
          }
        }
      } catch (err) {
        console.warn("spatial map sample refresh failed", err);
      } finally {
        state.loadingSpatialMap = false;
      }
    }
    async function loadFloors() {
      const payload = await fetchJson("/api/3d/floors");
      if (!payload || !payload.ok) return;
      state.floors = Array.isArray(payload.floors) ? payload.floors : [];
      state.floorsSignature = `${payload.ground_points}:${payload.z_min}:${payload.z_max}`;
      updateSliceBar();
      draw();
    }
    function updateSpatialMap(payload) {
      // /api/state no longer carries the 3D viewport samples (they only
      // change when the active map does); pull them from the dedicated
      // spatial_map endpoint, refetching only when the map identity changes.
      const backend = navigationBackendPayload(payload);
      const map3d = backend && backend.map_3d && typeof backend.map_3d === "object"
        ? backend.map_3d
        : {};
      const inlineSamples = Array.isArray(map3d.mapcloud_samples) && map3d.mapcloud_samples.length > 0;
      if (inlineSamples) {
        const next = buildSpatialMap(payload);
        const previousSignature = state.spatialMap && state.spatialMap.signature;
        state.spatialMap = next;
        state.spatialMapIdentity = spatialMapIdentity(payload, map3d, next && next.assetRecord);
        if (next && next.signature !== previousSignature) resetMapView(false);
        if (!state.selectedMapId) {
          updateLiveSpatialMapHeader();
        }
        return;
      }
      const assetRecord = activeDddmrAssetRecord(payload, map3d);
      const identity = spatialMapIdentity(payload, map3d, assetRecord);
      if (state.spatialMap && state.spatialMapIdentity === identity) return;
      state.spatialMapIdentity = identity;
      loadSpatialMapSamples().catch(console.warn);
    }
    function effectiveMapViewMode() {
      if (state.mapViewMode !== "3d") return "topdown";
      if (activePointerMode() || state.markPointer || state.localizationPopoverOpen) return "topdown";
      return "3d";
    }
    function getBaseView(rect = mapCanvasCssRect()) {
      const map = state.spatialMap;
      if (!map) return { scale: 1, ox: 0, oy: 0, rect };
      const scale = Math.min(rect.width / map.width, rect.height / map.height);
      const drawW = map.width * scale;
      const drawH = map.height * scale;
      return { scale, ox: (rect.width - drawW) / 2, oy: (rect.height - drawH) / 2, rect };
    }
    function getView(rect = mapCanvasCssRect()) {
      const base = getBaseView(rect);
      const zoom = clampZoom(state.view.zoom);
      const scale = base.scale * zoom;
      const map = state.spatialMap;
      if (!map) return {...base, zoom: 1, baseScale: base.scale};
      const drawW = map.width * scale;
      const drawH = map.height * scale;
      return {
        scale,
        baseScale: base.scale,
        zoom,
        ox: (base.rect.width - drawW) / 2 + state.view.panX,
        oy: (base.rect.height - drawH) / 2 + state.view.panY,
        rect: base.rect
      };
    }
    function clampZoom(value) {
      const zoom = Number(value);
      if (!Number.isFinite(zoom)) return 1;
      return Math.max(0.25, Math.min(12, zoom));
    }
    function clamp3dPitch(value) {
      const pitch = Number(value);
      if (!Number.isFinite(pitch)) return Math.PI / 5.2;
      // 0 = 正俯视；π/2 = 水平；>π/2 = 相机沉到地平线下，从下往上仰视（+z 仍朝上，不翻转）。
      // 单次连续拖拽：俯视 → 水平 → 仰视；yaw 不限。
      return Math.max(0, Math.min(3.10, pitch));
    }
    function updateZoomReadout(view = getView()) {
      if (!$("zoomReadout")) return;
      $("zoomReadout").textContent = `${Math.round((view.zoom || state.view.zoom || 1) * 100)}%`;
    }
    function clampView() {
      if (!state.spatialMap) return;
      state.view.zoom = clampZoom(state.view.zoom);
      state.view.pitch = clamp3dPitch(state.view.pitch);
      if (effectiveMapViewMode() === "3d") {
        const rect = mapCanvasCssRect();
        const limitX = Math.max(160, rect.width * 0.85);
        const limitY = Math.max(120, rect.height * 0.85);
        state.view.panX = Math.max(-limitX, Math.min(limitX, state.view.panX));
        state.view.panY = Math.max(-limitY, Math.min(limitY, state.view.panY));
        updateZoomReadout();
        return;
      }
      const view = getView();
      const drawW = state.spatialMap.width * view.scale;
      const drawH = state.spatialMap.height * view.scale;
      const margin = 80;
      if (drawW <= view.rect.width) {
        state.view.panX = 0;
      } else {
        const limitX = (drawW - view.rect.width) * 0.5 + margin;
        state.view.panX = Math.max(-limitX, Math.min(limitX, state.view.panX));
      }
      if (drawH <= view.rect.height) {
        state.view.panY = 0;
      } else {
        const limitY = (drawH - view.rect.height) * 0.5 + margin;
        state.view.panY = Math.max(-limitY, Math.min(limitY, state.view.panY));
      }
      updateZoomReadout();
    }
    function resetMapView(redraw = true) {
      state.view.zoom = 1;
      state.view.panX = 0;
      state.view.panY = 0;
      state.view.yaw = -Math.PI / 4;
      state.view.pitch = Math.PI / 5.2;
      state.view.sliceZ = null;
      updateZoomReadout();
      if (redraw) draw();
    }
    function setZoomAt(clientX, clientY, nextZoom) {
      if (!state.spatialMap) return;
      const oldView = getView();
      const rect = oldView.rect;
      const cx = clientX - rect.left;
      const cy = clientY - rect.top;
      const mx = (cx - oldView.ox) / oldView.scale;
      const my = (cy - oldView.oy) / oldView.scale;
      state.view.zoom = clampZoom(nextZoom);
      const newView = getView();
      state.view.panX += cx - (newView.ox + mx * newView.scale);
      state.view.panY += cy - (newView.oy + my * newView.scale);
      clampView();
      draw();
    }
    function zoomBy(factor) {
      const rect = mapCanvasCssRect();
      setZoomAt(rect.left + rect.width * 0.5, rect.top + rect.height * 0.5, state.view.zoom * factor);
    }
    function updateMapModeUi() {
      const modeBtn = $("mapViewModeBtn");
      if (modeBtn) {
        const threeD = state.mapViewMode === "3d";
        modeBtn.classList.toggle("active-tool", threeD);
        modeBtn.textContent = threeD ? "3D视角" : "俯视";
        modeBtn.title = threeD
          ? "当前为三维斜视点云；标点/重定位会自动用俯视"
          : "当前为俯视操作图；点击切到三维斜视点云";
      }
      $("cursor").textContent = state.view.panMode
        ? "平移模式"
        : (effectiveMapViewMode() === "3d" ? "PCD 点云视角：拖拽旋转，滚轮缩放，Shift/右键平移" : "拖拽空间视图取点和朝向");
      updateZoomReadout();
    }
    function centerMapOnWorld(x, y) {
      if (!state.spatialMap || !Number.isFinite(Number(x)) || !Number.isFinite(Number(y))) return;
      const mode = effectiveMapViewMode();
      const view = mode === "3d" ? get3dView() : getView();
      const target = mode === "3d"
        ? projectSpatial3d([Number(x), Number(y), state.spatialMap.minZ || 0], view)
        : worldToCanvasWithView(Number(x), Number(y), view);
      if (!target) return;
      state.view.panX += view.rect.width * 0.5 - target.x;
      state.view.panY += view.rect.height * 0.5 - target.y;
      clampView();
      draw();
    }
    function followRobotIfNeeded(activeTask) {
      const pose = freshPose();
      if (!state.followRobot || !activeTask || !pose || state.view.panMode || !canDrawLiveRobotLayer(state.latest)) return;
      centerMapOnWorld(pose.x, pose.y);
    }
    function worldToCanvasWithView(x, y, view) {
      const map = state.spatialMap;
      if (!map) return null;
      const mx = (x - map.origin.x) / map.resolution;
      const my = map.height - (y - map.origin.y) / map.resolution;
      return { x: view.ox + mx * view.scale, y: view.oy + my * view.scale };
    }
    function worldToCanvas(x, y) {
      return worldToCanvasWithView(x, y, getView());
    }
    function canvasToWorld(clientX, clientY) {
      const map = state.spatialMap;
      if (!map) return null;
      const rect = mapCanvasCssRect();
      const view = getView(rect);
      const cx = clientX - rect.left;
      const cy = clientY - rect.top;
      const mx = (cx - view.ox) / view.scale;
      const my = (cy - view.oy) / view.scale;
      if (mx < 0 || my < 0 || mx > map.width || my > map.height) return null;
      return {
        x: map.origin.x + mx * map.resolution,
        y: map.origin.y + (map.height - my) * map.resolution
      };
    }
    function normalizeYaw(yaw) {
      let value = Number(yaw);
      if (!Number.isFinite(value)) return 0;
      while (value > Math.PI) value -= Math.PI * 2;
      while (value <= -Math.PI) value += Math.PI * 2;
      return value;
    }
    function currentLocalizeYaw() {
      return normalizeYaw($("locYaw").value);
    }
    function currentMarkZ(fallback = 0.0) {
      const input = $("markZ");
      const raw = input ? String(input.value || "").trim() : "";
      if (!raw) return fallback;
      const value = Number(raw);
      return Number.isFinite(value) ? value : NaN;
    }
    function renderMarkPoseSummary() {
      const output = $("markPoseSummary");
      if (!output) return;
      const pose = state.markDraft;
      if (!pose) {
        output.className = "pose-readout";
        output.textContent = "未取点";
        return;
      }
      output.className = "pose-readout ready";
      const zText = Number.isFinite(Number(pose.z)) ? Number(pose.z).toFixed(3) : "无效";
      output.textContent = `X ${pose.x.toFixed(3)}  /  Y ${pose.y.toFixed(3)}  /  Z ${zText}  /  朝向 ${pose.yaw.toFixed(3)} rad`;
    }
    function setMarkDraft(pose, message, source = "map_click") {
      const z = Number.isFinite(Number(pose.z)) ? Number(pose.z) : currentMarkZ(0.0);
      state.markDraft = {
        x: Number(pose.x),
        y: Number(pose.y),
        z,
        yaw: normalizeYaw(pose.yaw)
      };
      if ($("markZ")) $("markZ").value = z.toFixed(3);
      state.markDraftSource = source;
      const shownFloor = displayedMapFloor();
      if (source === "map_click" && shownFloor) setFloorControlValue("markFloor", shownFloor);
      renderMarkPoseSummary();
      $("cursor").textContent = message || `x ${state.markDraft.x.toFixed(3)} / y ${state.markDraft.y.toFixed(3)} / z ${state.markDraft.z.toFixed(3)} / 朝向 ${state.markDraft.yaw.toFixed(3)} rad`;
      updateMarkControls();
      draw();
    }
    function setLocalizeDraft(pose, message) {
      state.localizeDraft = {
        x: Number(pose.x),
        y: Number(pose.y),
        yaw: normalizeYaw(pose.yaw)
      };
      $("locXY").value = `${state.localizeDraft.x.toFixed(3)}, ${state.localizeDraft.y.toFixed(3)}`;
      $("locYaw").value = state.localizeDraft.yaw.toFixed(4);
      $("cursor").textContent = message || `定位 x ${state.localizeDraft.x.toFixed(3)} / y ${state.localizeDraft.y.toFixed(3)} / 朝向 ${state.localizeDraft.yaw.toFixed(3)} rad`;
      draw();
    }
    function activeTabName() {
      const active = document.querySelector("button.tab.active");
      return active ? active.dataset.tab : "";
    }
    function activePointerMode() {
      if (state.localizationPopoverOpen) return "localize";
      const tab = activeTabName();
      if (tab === "marks") return "mark";
      if (tab === "work") return state.workPointerMode === "mark" ? "mark" : "localize";
      return null;
    }
    function updatePointerModeUi() {
      canvas.classList.toggle("pointing", Boolean(activePointerMode()));
    }
    function setWorkPointerMode(mode) {
      state.workPointerMode = mode === "mark" ? "mark" : "localize";
      const localizeBtn = $("workModeLocalizeBtn");
      const markBtn = $("workModeMarkBtn");
      if (localizeBtn) localizeBtn.classList.toggle("active-tool", state.workPointerMode === "localize");
      if (markBtn) markBtn.classList.toggle("active-tool", state.workPointerMode === "mark");
      $("cursor").textContent = state.workPointerMode === "localize"
        ? "重定位模式：拖拽地图设置位置和朝向"
        : "标点模式：拖拽地图设置位置和朝向";
      updatePointerModeUi();
      draw();
    }
    function drawArrow(pose, options = {}) {
      if (!Number.isFinite(Number(pose.x)) || !Number.isFinite(Number(pose.y))) return;
      let p;
      if (effectiveMapViewMode() === "3d") {
        const view3d = get3dView();
        const z = Number.isFinite(Number(pose.z)) ? Number(pose.z) : (state.spatialMap ? Number(state.spatialMap.minZ) : 0);
        p = projectSpatial3d([Number(pose.x), Number(pose.y), z], view3d);
      } else {
        p = worldToCanvas(pose.x, pose.y);
      }
      if (!p) return;
      const color = options.color || "#0f6bff";
      const size = options.size || 1.0;
      const label = options.label || "";
      ctx.save();
      ctx.translate(p.x, p.y);
      ctx.rotate(-(Number(pose.yaw) || 0));
      ctx.fillStyle = color;
      ctx.strokeStyle = options.stroke || "#ffffff";
      ctx.lineWidth = options.lineWidth || 2;
      ctx.beginPath();
      ctx.moveTo(15 * size, 0);
      ctx.lineTo(-10 * size, -8 * size);
      ctx.lineTo(-6 * size, 0);
      ctx.lineTo(-10 * size, 8 * size);
      ctx.closePath();
      ctx.fill();
      ctx.stroke();
      ctx.restore();
      if (label) {
        ctx.save();
        ctx.font = "12px system-ui, sans-serif";
        ctx.fillStyle = "#17212b";
        ctx.fillText(label, p.x + 11, p.y - 9);
        ctx.restore();
      }
    }
    function drawPath(path, options = {}) {
      if (!path || !path.points || path.points.length < 2) return;
      ctx.save();
      ctx.strokeStyle = options.color || "#f97316";
      ctx.lineWidth = options.lineWidth || 3;
      if (options.dash) ctx.setLineDash(options.dash);
      ctx.lineCap = "round";
      ctx.lineJoin = "round";
      ctx.beginPath();
      let started = false;
      for (const point of path.points) {
        const p = worldToCanvas(point.x, point.y);
        if (!p) continue;
        if (!started) { ctx.moveTo(p.x, p.y); started = true; }
        else ctx.lineTo(p.x, p.y);
      }
      ctx.stroke();
      ctx.restore();
    }
    function drawObstacles(items) {
      if (!items || items.length === 0 || !state.spatialMap) return;
      const view = getView();
      ctx.save();
      for (const item of items) {
        const p = worldToCanvasWithView(item.x, item.y, view);
        if (!p) continue;
        const radius = Math.max(5, Math.min(22, (item.scale_x || 0.4) / state.spatialMap.resolution * view.scale * 0.5));
        ctx.fillStyle = "rgba(185, 28, 28, 0.82)";
        ctx.strokeStyle = "#ffffff";
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(p.x, p.y, radius, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();
      }
      ctx.restore();
    }
    function drawAnnotations() {
      if (!state.annotations || !state.spatialMap) return;
      for (const item of state.annotations) {
        const pose = item.pose || {};
        const color = annotationTypeColor(item);
        const label = item.label || annotationTypeLabel(item);
        drawArrow(
          {x: Number(pose.x), y: Number(pose.y), yaw: Number(pose.yaw) || 0},
          {color, size: 0.72, label}
        );
      }
    }
    function drawMarkDraft() {
      if (!state.markDraft) return;
      drawArrow(state.markDraft, {
        color: "#16a34a",
        stroke: "#f8fafc",
        lineWidth: 2.5,
        size: 0.92,
        label: "待保存"
      });
    }
    function drawLocalizeDraft() {
      if (!state.localizeDraft) return;
      drawArrow(state.localizeDraft, {
        color: "#dc2626",
        stroke: "#fef2f2",
        lineWidth: 2.5,
        size: 1.0,
        label: "定位"
      });
    }
    function drawActiveWaypointTarget() {
      const waypoint = state.latest
        && state.latest.active_waypoint
        && state.latest.active_waypoint.parsed
        && state.latest.active_waypoint.parsed.waypoint;
      const pose = waypoint && waypoint.pose;
      if (!pose) return;
      const waypointFloor = waypoint.floor ? String(waypoint.floor).trim() : "";
      const shownFloor = displayedMapFloor();
      if (shownFloor && waypointFloor && shownFloor !== waypointFloor) return;
      drawArrow(
        {x: Number(pose.x), y: Number(pose.y), yaw: Number(pose.yaw) || 0},
        {
          color: "#f97316",
          stroke: "#fff7ed",
          lineWidth: 3,
          size: 1.08,
          label: `目标 ${waypoint.label || ""}`.trim()
        }
      );
    }
    function drawNavFeedbackPose() {
      if (!canDrawLiveRobotLayer()) return;
      const active = state.latest && state.latest.active_task;
      const waypoint = state.latest
        && state.latest.active_waypoint
        && state.latest.active_waypoint.parsed;
      const feedback = (waypoint && waypoint.nav_feedback) || (active && active.last_nav_feedback) || null;
      if (!feedback || !Number.isFinite(Number(feedback.pose_x)) || !Number.isFinite(Number(feedback.pose_y))) return;
      drawArrow(
        {
          x: Number(feedback.pose_x),
          y: Number(feedback.pose_y),
          yaw: Number.isFinite(Number(feedback.pose_yaw)) ? Number(feedback.pose_yaw) : 0
        },
        {
          color: "#7c3aed",
          stroke: "#f5f3ff",
          lineWidth: 2,
          size: 0.84,
          label: "导航反馈"
        }
      );
    }
    function drawScanOverlay() {
      if (!state.scanOverlay || !state.spatialMap || !state.latest) return;
      const mclOwned = localizationOwner() === "official_mcl";
      const cloud = state.latest.live_cloud;
      if (mclOwned) {
        // 3D 链路用官方实时点云的体坐标系切片做俯视轮廓，不依赖原厂 2D /scan。
        if (!cloud || !Array.isArray(cloud.samples) || !cloud.samples.length) return;
        const nowSec = state.latest.received_at || Date.now() / 1000;
        if (nowSec - (Number(cloud.last_update) || 0) > 3.0) return;
      } else if (!state.latest.scan) {
        return;
      }
      const points = mclOwned
        ? cloud.samples.map(pt => ({x: Number(pt[0]), y: Number(pt[1])}))
        : (state.latest.scan.points || []);
      if (!points.length) return;
      // A new red draft is a separate operator transaction. Do not let an old
      // confirmed localization hide its preview or draw the stale blue scan.
      const usingDraft = localizationDraftActive();
      if (!usingDraft && !canDrawLiveRobotLayer()) return;
      if (usingDraft && !isViewingRobotFloor()) return;
      const pose = usingDraft ? state.localizeDraft : freshPose();
      if (!pose || !Number.isFinite(Number(pose.x)) || !Number.isFinite(Number(pose.y))) return;
      const yaw = normalizeYaw(pose.yaw || 0);
      const cosYaw = Math.cos(yaw);
      const sinYaw = Math.sin(yaw);
      const offset = state.latest.scan_overlay_offset || {};
      const offX = Number(offset.x || 0);
      const offY = Number(offset.y || 0);
      const offYaw = normalizeYaw(offset.yaw || 0);
      const cosOff = Math.cos(offYaw);
      const sinOff = Math.sin(offYaw);
      const view = getView();
      ctx.save();
      ctx.fillStyle = usingDraft ? "rgba(220, 38, 38, 0.72)" : "rgba(14, 165, 233, 0.78)";
      const radius = Math.max(1.4, Math.min(3.2, view.scale * 1.6));
      for (const point of points) {
        const px = Number(point.x);
        const py = Number(point.y);
        if (!Number.isFinite(px) || !Number.isFinite(py)) continue;
        const bx = offX + cosOff * px - sinOff * py;
        const by = offY + sinOff * px + cosOff * py;
        const wx = Number(pose.x) + cosYaw * bx - sinYaw * by;
        const wy = Number(pose.y) + sinYaw * bx + cosYaw * by;
        const p = worldToCanvasWithView(wx, wy, view);
        if (!p) continue;
        ctx.fillRect(p.x - radius * 0.5, p.y - radius * 0.5, radius, radius);
      }
      ctx.restore();
    }
    function liveRobotPose3d() {
      const latest = state.latest;
      if (!latest || !state.spatialMap) return null;
      if (!canDrawLiveRobotLayer(latest) || !hasFreshPose(latest)) return null;
      return stableRobotDisplayPose(latest.pose, latest.active_task || null);
    }
    function drawLiveCloud3d(map, view) {
      const latest = state.latest;
      if (!latest || !map) return;
      const cloud = latest.live_cloud;
      if (!cloud || !Array.isArray(cloud.samples) || !cloud.samples.length) return;
      const pose = liveRobotPose3d();
      if (!pose) return;
      const now = (latest.received_at || Date.now() / 1000);
      const age = now - (Number(cloud.last_update) || 0);
      if (age > 3.0) return;
      const yaw = normalizeYaw(pose.yaw || 0);
      const cosYaw = Math.cos(yaw);
      const sinYaw = Math.sin(yaw);
      const groundZ = Number(map.minZ) || 0;
      const alpha = Math.max(0.25, Math.min(0.9, 1.1 - age * 0.35));
      ctx.save();
      for (const point of cloud.samples) {
        const px = Number(point[0]);
        const py = Number(point[1]);
        const pz = Number(point[2]);
        if (!Number.isFinite(px) || !Number.isFinite(py) || !Number.isFinite(pz)) continue;
        const bx = cosYaw * px - sinYaw * py;
        const by = sinYaw * px + cosYaw * py;
        const wx = Number(pose.x) + bx;
        const wy = Number(pose.y) + by;
        const wz = groundZ + pz;
        const projected = projectSpatial3d([wx, wy, wz], view);
        if (!projected) continue;
        const color = spatialHeightColor(pz, map, alpha);
        ctx.fillStyle = color;
        ctx.fillRect(projected.x - 1.1, projected.y - 1.1, 2.2, 2.2);
      }
      ctx.restore();
    }
    function drawRobotModel3d(map, view) {
      if (!map) return;
      const pose = liveRobotPose3d();
      if (!pose) return;
      const yaw = normalizeYaw(pose.yaw || 0);
      const cosYaw = Math.cos(yaw);
      const sinYaw = Math.sin(yaw);
      const px = Number(pose.x);
      const py = Number(pose.y);
      const zGround = Number(map.minZ) || 0;
      // 比例取自 m20pro_description/urdf/M20.urdf（轮足构型）。
      const bodyZ = zGround + 0.42;
      const wheelZ = zGround + 0.09;
      const toWorld = (lx, ly, lz) => [
        px + cosYaw * lx - sinYaw * ly,
        py + sinYaw * lx + cosYaw * ly,
        lz,
      ];
      const rotAxis = (lx, ly, lz) => [
        cosYaw * lx - sinYaw * ly,
        sinYaw * lx + cosYaw * ly,
        lz,
      ];
      const LIGHT = [-0.42, -0.5, 0.76];
      const faces = [];
      const strokes = [];
      function shade(rgb, n) {
        const dot = Math.max(0, n[0] * LIGHT[0] + n[1] * LIGHT[1] + n[2] * LIGHT[2]);
        const k = 0.52 + 0.48 * dot;
        return `rgba(${Math.round(rgb[0] * k)}, ${Math.round(rgb[1] * k)}, ${Math.round(rgb[2] * k)}, 0.96)`;
      }
      function pushFace(pts, rgb, stroke) {
        const projected = pts.map(p => projectSpatial3d(p, view));
        if (projected.some(p => !p)) return;
        const [a, b, c] = pts;
        const u = [b[0] - a[0], b[1] - a[1], b[2] - a[2]];
        const v = [c[0] - a[0], c[1] - a[1], c[2] - a[2]];
        let n = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]];
        const len = Math.hypot(n[0], n[1], n[2]) || 1;
        n = [n[0] / len, n[1] / len, n[2] / len];
        const depth = projected.reduce((s, p) => s + p.depth, 0) / projected.length;
        faces.push({ depth, fill: shade(rgb, n), projected, stroke });
      }
      function pushBoxCorners(c8, rgb, stroke) {
        const F = [[0, 1, 3, 2], [4, 5, 7, 6], [0, 1, 5, 4], [2, 3, 7, 6], [0, 2, 6, 4], [1, 3, 7, 5]];
        for (const f of F) pushFace([c8[f[0]], c8[f[1]], c8[f[2]], c8[f[3]]], rgb, stroke);
      }
      function pushBox(cx, cy, cz, dx, dy, dz, rgb, stroke) {
        const c8 = [];
        for (const sx of [-0.5, 0.5]) for (const sy of [-0.5, 0.5]) for (const sz of [-0.5, 0.5]) {
          c8.push(toWorld(cx + sx * dx, cy + sy * dy, cz + sz * dz));
        }
        pushBoxCorners(c8, rgb, stroke);
      }
      function pushSegment(a, b, w, th, rgb) {
        const dy = b[1] - a[1];
        const dz = b[2] - a[2];
        const len = Math.hypot(dy, dz) || 1;
        const e1 = [0, dy / len, dz / len];
        const e2 = [0, -e1[2], e1[1]];
        const c8 = [];
        for (const s of [-0.5, 0.5]) {
          for (const wS of [-0.5, 0.5]) {
            for (const tS of [-0.5, 0.5]) {
              c8.push(toWorld(
                a[0] + (b[0] - a[0]) * (s + 0.5) + tS * th,
                a[1] + (b[1] - a[1]) * (s + 0.5) + e2[1] * w * wS,
                a[2] + (b[2] - a[2]) * (s + 0.5) + e2[2] * w * wS
              ));
            }
          }
        }
        pushBoxCorners(c8, rgb, null);
      }
      function pushDisc(center, axis, r, rgb, segments = 12) {
        let u;
        if (Math.abs(axis[2]) < 0.9) u = [0, 0, 1]; else u = [1, 0, 0];
        let ux = [
          u[0] - axis[0] * (u[0] * axis[0] + u[1] * axis[1] + u[2] * axis[2]),
          u[1] - axis[1] * (u[0] * axis[0] + u[1] * axis[1] + u[2] * axis[2]),
          u[2] - axis[2] * (u[0] * axis[0] + u[1] * axis[1] + u[2] * axis[2]),
        ];
        const ul = Math.hypot(ux[0], ux[1], ux[2]) || 1;
        ux = [ux[0] / ul, ux[1] / ul, ux[2] / ul];
        const uw = [
          axis[1] * ux[2] - axis[2] * ux[1],
          axis[2] * ux[0] - axis[0] * ux[2],
          axis[0] * ux[1] - axis[1] * ux[0],
        ];
        const ring = [];
        for (let i = 0; i < segments; i += 1) {
          const ang = (i / segments) * Math.PI * 2;
          const ca = Math.cos(ang) * r;
          const sa = Math.sin(ang) * r;
          ring.push(toWorld(
            center[0] + ux[0] * ca + uw[0] * sa,
            center[1] + ux[1] * ca + uw[1] * sa,
            center[2] + ux[2] * ca + uw[2] * sa
          ));
        }
        pushFace(ring, rgb, null);
        return ring;
      }
      // 地面接触阴影
      const shadow = [];
      for (let i = 0; i < 16; i += 1) {
        const ang = (i / 16) * Math.PI * 2;
        shadow.push(toWorld(Math.cos(ang) * 0.46, Math.sin(ang) * 0.30, zGround + 0.004));
      }
      const shadowPts = shadow.map(p => projectSpatial3d(p, view)).filter(Boolean);
      if (shadowPts.length === 16) {
        faces.push({
          depth: Math.max(...shadowPts.map(p => p.depth)) + 0.05,
          fill: "rgba(2, 6, 12, 0.4)",
          projected: shadowPts,
          stroke: null,
        });
      }
      const BODY = [38, 48, 62];
      const DECK = [56, 68, 86];
      const HEAD = [70, 82, 100];
      const LEG = [46, 56, 72];
      const LEG2 = [62, 74, 92];
      const DARK = [18, 24, 34];
      const ACCENT = [232, 150, 40];
      // 躯干：主盒 + 前斜切楔形 + 顶舱 + 尾部提手
      pushBox(-0.03, 0, bodyZ, 0.56, 0.24, 0.16, BODY, "rgba(148,163,184,0.5)");
      pushFace([
        toWorld(0.25, -0.12, bodyZ + 0.08), toWorld(0.25, 0.12, bodyZ + 0.08),
        toWorld(0.40, 0.10, bodyZ - 0.02), toWorld(0.40, -0.10, bodyZ - 0.02),
      ], DECK, null);
      pushFace([
        toWorld(0.25, -0.12, bodyZ - 0.08), toWorld(0.25, 0.12, bodyZ - 0.08),
        toWorld(0.40, 0.10, bodyZ - 0.02), toWorld(0.40, -0.10, bodyZ - 0.02),
      ], BODY, null);
      pushBox(0.02, 0, bodyZ + 0.115, 0.30, 0.16, 0.07, DECK, "rgba(148,163,184,0.4)");
      pushBox(-0.36, 0, bodyZ + 0.10, 0.10, 0.18, 0.03, LEG2, null);
      // 头部 + 传感条 + 顶部激光雷达包
      pushBox(0.40, 0, bodyZ + 0.02, 0.15, 0.14, 0.12, HEAD, "rgba(203,213,225,0.6)");
      pushFace([
        toWorld(0.476, -0.05, bodyZ + 0.05), toWorld(0.476, 0.05, bodyZ + 0.05),
        toWorld(0.476, 0.05, bodyZ + 0.01), toWorld(0.476, -0.05, bodyZ + 0.01),
      ], ACCENT, null);
      pushDisc([-0.10, 0, bodyZ + 0.185], [0, 0, 1], 0.055, DARK, 12);
      pushDisc([-0.10, 0, bodyZ + 0.205], [0, 0, 1], 0.045, LEG2, 12);
      // 四条腿：髋块 + 大腿 + 膝盘 + 小腿 + 轮（胎面+轮毂+辐条）
      for (const [sx, sy] of [[1, 1], [1, -1], [-1, 1], [-1, -1]]) {
        const hip = [0.314 * sx, 0.069 * sy, bodyZ - 0.03];
        const knee = [0.314 * sx, 0.170 * sy, bodyZ - 0.22];
        const wheelC = [0.314 * sx, 0.110 * sy, wheelZ];
        pushBox(hip[0], hip[1], hip[2], 0.09, 0.07, 0.10, LEG, null);
        pushSegment(hip, knee, 0.055, 0.05, LEG);
        pushDisc([knee[0], knee[1] + 0.028 * sy, knee[2]], rotAxis(0, sy, 0), 0.045, ACCENT, 10);
        pushSegment(knee, wheelC, 0.042, 0.036, LEG2);
        const axis = rotAxis(0, sy, 0);
        pushDisc([wheelC[0], wheelC[1] + 0.02 * sy, wheelC[2]], axis, 0.09, DARK, 14);
        pushDisc([wheelC[0], wheelC[1] + 0.024 * sy, wheelC[2]], axis, 0.035, ACCENT, 10);
        for (let sIdx = 0; sIdx < 4; sIdx += 1) {
          const ang = (sIdx / 4) * Math.PI * 2 + 0.4;
          const ex = Math.cos(ang) * 0.075;
          const ez = Math.sin(ang) * 0.075;
          const a3 = [wheelC[0] + ex, wheelC[1] + 0.024 * sy, wheelC[2] + ez];
          const b3 = [wheelC[0] - ex, wheelC[1] + 0.024 * sy, wheelC[2] - ez];
          const pa = projectSpatial3d(toWorld(a3[0], a3[1], a3[2]), view);
          const pb = projectSpatial3d(toWorld(b3[0], b3[1], b3[2]), view);
          if (pa && pb) {
            strokes.push({ depth: (pa.depth + pb.depth) / 2, pa, pb, color: "rgba(148,163,184,0.8)", width: Math.max(1, 0.012 * view.scale) });
          }
        }
      }
      faces.sort((a, b) => b.depth - a.depth);
      strokes.sort((a, b) => b.depth - a.depth);
      ctx.save();
      for (const f of faces) {
        ctx.beginPath();
        ctx.moveTo(f.projected[0].x, f.projected[0].y);
        for (let i = 1; i < f.projected.length; i += 1) ctx.lineTo(f.projected[i].x, f.projected[i].y);
        ctx.closePath();
        ctx.fillStyle = f.fill;
        ctx.fill();
        if (f.stroke) {
          ctx.strokeStyle = f.stroke;
          ctx.lineWidth = 1;
          ctx.stroke();
        }
      }
      for (const s of strokes) {
        ctx.beginPath();
        ctx.moveTo(s.pa.x, s.pa.y);
        ctx.lineTo(s.pb.x, s.pb.y);
        ctx.strokeStyle = s.color;
        ctx.lineWidth = s.width;
        ctx.stroke();
      }
      ctx.restore();
    }
    function spatialHeightRatio(z, map) {
      const range = Math.max(0.001, Number(map.maxZ) - Number(map.minZ));
      return Math.max(0, Math.min(1, (Number(z) - Number(map.minZ)) / range));
    }
    function spatialHeightColor(z, map, alpha = 0.92) {
      const ratio = spatialHeightRatio(z, map);
      const red = Math.round(25 + ratio * 224);
      const green = Math.round(134 + Math.max(0, 1 - Math.abs(ratio - 0.42) * 2.4) * 78);
      const blue = Math.round(190 - ratio * 142);
      return `rgba(${red}, ${green}, ${blue}, ${alpha})`;
    }
    function spatialPointColor(z, map) {
      return spatialHeightColor(z, map, 0.9);
    }
    function spatialGroundCellColor(cell, alpha = 0.68) {
      const shade = Math.round(82 + Math.max(0, Math.min(1, cell.density || 0)) * 58);
      return `rgba(${shade}, ${shade + 13}, ${shade + 20}, ${alpha})`;
    }
    function drawCanvasBackground(rect, mode) {
      if (mode === "3d") {
        ctx.fillStyle = "#07111f";
      } else {
        ctx.fillStyle = "#e4e8eb";
      }
      ctx.fillRect(0, 0, rect.width, rect.height);
    }
    function get3dView(rect = mapCanvasCssRect()) {
      const map = state.spatialMap;
      if (!map) return {rect, scale: 1, cx: rect.width * 0.5, cy: rect.height * 0.5};
      const bounds = map.bounds || {
        minX: map.origin.x,
        maxX: map.origin.x + map.width * map.resolution,
        minY: map.origin.y,
        maxY: map.origin.y + map.height * map.resolution
      };
      const minZ = Number(map.minZ);
      const maxZ = Number(map.maxZ);
      const extent = Math.max(bounds.maxX - bounds.minX, bounds.maxY - bounds.minY, (maxZ - minZ) * 2.8, 0.8);
      return {
        rect,
        zoom: clampZoom(state.view.zoom),
        scale: Math.min(rect.width, rect.height) / Math.max(extent * 1.35, 1.0) * clampZoom(state.view.zoom),
        cx: rect.width * 0.5 + state.view.panX,
        cy: rect.height * 0.56 + state.view.panY,
        center: {
          x: (bounds.minX + bounds.maxX) * 0.5,
          y: (bounds.minY + bounds.maxY) * 0.5,
          z: (minZ + maxZ) * 0.5
        },
        yaw: Number.isFinite(Number(state.view.yaw)) ? Number(state.view.yaw) : -Math.PI / 4,
        pitch: clamp3dPitch(state.view.pitch)
      };
    }
    function projectSpatial3d(point, view) {
      const x = Number(Array.isArray(point) ? point[0] : point.x);
      const y = Number(Array.isArray(point) ? point[1] : point.y);
      const z = Number(Array.isArray(point) ? point[2] : (point.z || 0));
      if (![x, y, z].every(Number.isFinite)) return null;
      const dx = x - view.center.x;
      const dy = y - view.center.y;
      const dz = z - view.center.z;
      const cyaw = Math.cos(view.yaw);
      const syaw = Math.sin(view.yaw);
      const rx = dx * cyaw - dy * syaw;
      const ry = dx * syaw + dy * cyaw;
      const cp = Math.cos(view.pitch);
      const sp = Math.sin(view.pitch);
      const py = ry * cp + dz * sp;
      // 深度约定：depth 越大 = 离相机越远（面排序/点云排序/地面阴影统一）。
      // pitch∈[0,π/2) 相机在地平线上方俯视；pitch>π/2 相机沉到地平线下仰视。
      // 注意此前符号写反，导致 pitch=0 实为仰视、pitch→π 反而渲染成倒转的俯视。
      const depth = ry * sp - dz * cp;
      return {
        x: view.cx + rx * view.scale,
        y: view.cy - py * view.scale,
        depth,
        z
      };
    }
    function draw3dGrid(map, view) {
      const bounds = map.bounds || {
        minX: map.origin.x,
        maxX: map.origin.x + map.width * map.resolution,
        minY: map.origin.y,
        maxY: map.origin.y + map.height * map.resolution
      };
      const corners = [
        [bounds.minX, bounds.minY, map.minZ],
        [bounds.maxX, bounds.minY, map.minZ],
        [bounds.maxX, bounds.maxY, map.minZ],
        [bounds.minX, bounds.maxY, map.minZ]
      ].map(point => projectSpatial3d(point, view)).filter(Boolean);
      if (corners.length !== 4) return;
      ctx.save();
      ctx.strokeStyle = "rgba(148, 163, 184, 0.16)";
      ctx.lineWidth = 0.9;
      ctx.beginPath();
      ctx.moveTo(corners[0].x, corners[0].y);
      for (let index = 1; index < corners.length; index += 1) ctx.lineTo(corners[index].x, corners[index].y);
      ctx.closePath();
      ctx.stroke();
      const gridLines = 3;
      ctx.strokeStyle = "rgba(148, 163, 184, 0.08)";
      for (let index = 1; index < gridLines; index += 1) {
        const x = bounds.minX + (bounds.maxX - bounds.minX) * (index / gridLines);
        const a = projectSpatial3d([x, bounds.minY, map.minZ], view);
        const b = projectSpatial3d([x, bounds.maxY, map.minZ], view);
        if (a && b) {
          ctx.beginPath();
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(b.x, b.y);
          ctx.stroke();
        }
        const y = bounds.minY + (bounds.maxY - bounds.minY) * (index / gridLines);
        const c = projectSpatial3d([bounds.minX, y, map.minZ], view);
        const d = projectSpatial3d([bounds.maxX, y, map.minZ], view);
        if (c && d) {
          ctx.beginPath();
          ctx.moveTo(c.x, c.y);
          ctx.lineTo(d.x, d.y);
          ctx.stroke();
        }
      }
      ctx.restore();
    }
    function drawSpatialDiamond(x, y, sizeX, sizeY, fillStyle, strokeStyle = "") {
      ctx.beginPath();
      ctx.moveTo(x, y - sizeY);
      ctx.lineTo(x + sizeX, y);
      ctx.lineTo(x, y + sizeY);
      ctx.lineTo(x - sizeX, y);
      ctx.closePath();
      ctx.fillStyle = fillStyle;
      ctx.fill();
      if (strokeStyle) {
        ctx.strokeStyle = strokeStyle;
        ctx.stroke();
      }
    }
    function spatialPcdColor(z, map, layer = "cloud", alpha = 0.92) {
      if (layer === "ground") return `rgba(148, 163, 184, ${alpha})`;
      const ratio = spatialHeightRatio(z, map);
      const stops = [
        [56, 189, 248],
        [45, 212, 191],
        [163, 230, 53],
        [251, 146, 60]
      ];
      const scaled = ratio * (stops.length - 1);
      const index = Math.max(0, Math.min(stops.length - 2, Math.floor(scaled)));
      const t = scaled - index;
      const a = stops[index];
      const b = stops[index + 1];
      const red = Math.round(a[0] + (b[0] - a[0]) * t);
      const green = Math.round(a[1] + (b[1] - a[1]) * t);
      const blue = Math.round(a[2] + (b[2] - a[2]) * t);
      return `rgba(${red}, ${green}, ${blue}, ${alpha})`;
    }
    function drawSpatialRenderCells3d(map, view) {
      const groundPoints = Array.isArray(map.mapground) ? map.mapground : [];
      const cloudPoints = Array.isArray(map.mapcloud) ? map.mapcloud : [];
      const totalPoints = groundPoints.length + cloudPoints.length;
      if (!totalPoints) return;
      const baseSize = totalPoints > 12000 ? 0.56 : (totalPoints > 5000 ? 0.66 : 0.78);
      const pointSize = Math.max(0.45, Math.min(1.25, baseSize * Math.sqrt(view.zoom || 1)));
      const projectedPoints = [];
      const addPoint = (point, layer) => {
        const projected = projectSpatial3d(point, view);
        if (!projected) return;
        if (
          projected.x < -8 || projected.y < -8
          || projected.x > view.rect.width + 8
          || projected.y > view.rect.height + 8
        ) return;
        projectedPoints.push({
          x: projected.x,
          y: projected.y,
          z: projected.z,
          depth: projected.depth,
          layer,
          size: layer === "ground" ? pointSize * 0.72 : pointSize
        });
      };
      for (const point of groundPoints) addPoint(point, "ground");
      for (const point of cloudPoints) addPoint(point, "cloud");
      projectedPoints.sort((a, b) => b.depth - a.depth);
      ctx.save();
      ctx.globalCompositeOperation = "source-over";
      for (const point of projectedPoints) {
        ctx.fillStyle = spatialPcdColor(point.z, map, point.layer, point.layer === "ground" ? 0.48 : 0.85);
        const size = point.size;
        ctx.fillRect(point.x - size * 0.5, point.y - size * 0.5, size, size);
      }
      ctx.restore();
    }
    function drawSpatialRenderCellsTopdown(map, view) {
      const model = map.renderModel || {};
      const cells = Array.isArray(model.cells) ? model.cells : [];
      if (!cells.length) return;
      const [sliceLo, sliceHi] = sliceWindow(map);
      ctx.save();
      const cellPixels = Math.max(1.4, Math.min(12, ((model.cellSize || 0.1) / map.resolution) * view.scale * 1.05));
      for (const cell of cells) {
        if (!cell.hasGround || cell.hasCloud) continue;
        if (cell.baseZ > sliceHi || cell.topZ < sliceLo) continue;
        const projected = worldToCanvasWithView(cell.x, cell.y, view);
        if (!projected) continue;
        const alpha = 0.34 + Math.max(0, Math.min(1, cell.density || 0)) * 0.28;
        ctx.fillStyle = spatialGroundCellColor(cell, alpha);
        ctx.fillRect(projected.x - cellPixels * 0.5, projected.y - cellPixels * 0.5, cellPixels, cellPixels);
      }
      for (const cell of cells) {
        if (!cell.hasCloud) continue;
        if (cell.baseZ > sliceHi || cell.topZ < sliceLo) continue;
        const projected = worldToCanvasWithView(cell.x, cell.y, view);
        if (!projected) continue;
        const size = cellPixels * (1.05 + Math.max(0, Math.min(1, cell.density || 0)) * 0.50);
        ctx.fillStyle = spatialHeightColor(cell.topZ, map, 0.78);
        ctx.fillRect(projected.x - size * 0.5, projected.y - size * 0.5, size, size);
      }
      ctx.strokeStyle = "rgba(58, 70, 78, 0.28)";
      ctx.lineWidth = 1;
      ctx.strokeRect(view.ox, view.oy, map.width * view.scale, map.height * view.scale);
      ctx.restore();
    }
    function draw() {
      const rect = syncMapCanvasBackingStore();
      const mode = effectiveMapViewMode();
      drawCanvasBackground(rect, mode);
      if (!state.spatialMap) {
        ctx.fillStyle = mode === "3d" ? "rgba(226, 232, 240, 0.72)" : "#667483";
        ctx.font = "15px system-ui, sans-serif";
        ctx.fillText("等待三维地图点云", 20, 30);
        return;
      }
      const view = getView(rect);
      updateZoomReadout(view);
      if (mode === "3d") {
        updateZoomReadout();
        const view3d = get3dView(rect);
        drawSpatialRenderCells3d(state.spatialMap, view3d);
        drawLiveCloud3d(state.spatialMap, view3d);
        drawRobotModel3d(state.spatialMap, view3d);
        drawAnnotations();
        drawMarkDraft();
        updateSliceBar();
        return;
      }
      drawSpatialRenderCellsTopdown(state.spatialMap, view);
      const latest = state.latest;
      const draftActive = localizationDraftActive();
      const canDrawLive = !draftActive && canDrawLiveRobotLayer(latest);
      if (!canDrawLive || !hasFreshPose(latest)) state.robotDisplayPose = null;
      if (canDrawLive) {
        drawPath(latest.path, {color: "rgba(249, 115, 22, 0.58)", lineWidth: 2.5, dash: [8, 6]});
        drawPath(latest.local_path, {color: "#facc15", lineWidth: 4});
        drawObstacles(latest.dynamic_obstacles);
      }
      drawScanOverlay();
      drawAnnotations();
      drawActiveWaypointTarget();
      drawNavFeedbackPose();
      drawMarkDraft();
      drawLocalizeDraft();
      if (canDrawLive && hasFreshPose(latest)) {
        const robotPose = stableRobotDisplayPose(latest.pose, latest.active_task || null);
        if (robotPose) drawArrow(robotPose);
      }
      updateSliceBar();
    }
    async function loadFileMap(mapId) {
      if (!mapId) {
        state.selectedMapId = null;
        state.map = null;
        state.markDraft = null;
        state.markDraftSource = "map_click";
        renderMarkPoseSummary();
        updateLiveSpatialMapHeader();
        renderUnifiedSpaceView();
        updateMapModeUi();
        updateMarkControls();
        return;
      }
      const map = mapRecordById(mapId);
      if (!map) throw {ok: false, message: `楼层地图记录 ${mapId} 不存在`};
      state.map = map;
      state.selectedMapId = mapId;
      state.markDraft = null;
      state.markDraftSource = "map_click";
      renderMarkPoseSummary();
      if (map.floor) setFloorControlValue("markFloor", map.floor);
      renderUnifiedSpaceView();
      updateLiveSpatialMapHeader();
      updateMapModeUi();
      await loadAnnotations();
      updateMarkControls();
      resetMapView(false);
      resizeCanvas();
    }
    function navigationBackendPayload(payload = state.latest) {
      const fallback = {
        backend: "dddmr_3d",
        active: false,
        ready: false,
        motion_enabled: false,
        reason: "dddmr_bridge_status_missing",
        command_mux: {seen: false, mode: "", reason: "", output_nonzero: false, updated_at: null},
        gnss: {ready: false, anchor_usable: false, used_for_motion: false, code: "gnss_status_missing"},
        edge_cloud: {ready: false, code: "dddmr_edge_cloud_unavailable", finite_points: 0, frame_id: ""},
        map_3d: {ready: false, mapcloud_ready: false, mapground_ready: false, mapcloud_points: 0, mapground_points: 0},
        runtime: {seen: false, backend: "", ready: false, state: "", code: "", tf_ready: false, tf_code: ""},
        field_test: {
          ready: false,
          reason: "dddmr_bridge_status_missing",
          mode: "move",
          runtime_backend: "",
          notes: [],
          acceptance: {
            ready: false,
            reason: "dddmr_bridge_status_missing",
            blocked_by: ["field_test"],
            field_test_ready: false,
            field_test_reason: "dddmr_bridge_status_missing",
            mode: "move",
            runtime_backend: "",
            active_task: {seen: false, running: false, task_id: "", status: "", task_name: "", multi_floor: false},
            command_mux: {seen: false, mode: "", reason: "", output_nonzero: false, updated_at: null}
          }
        },
        action_server_ready: false,
        action_type_available: false,
        goal_active: false,
        bridge_seen: false
      };
      const value = payload && payload.navigation_backend;
      return value && typeof value === "object" ? {...fallback, ...value,
        gnss: {...fallback.gnss, ...(value.gnss || {})},
        edge_cloud: {...fallback.edge_cloud, ...(value.edge_cloud || {})},
        map_3d: {...fallback.map_3d, ...(value.map_3d || {})},
        runtime: {...fallback.runtime, ...(value.runtime || {})},
        command_mux: {...fallback.command_mux, ...(value.command_mux || {})},
        field_test: {
          ...fallback.field_test,
          ...(value.field_test || {}),
          acceptance: {...fallback.field_test.acceptance, ...((value.field_test || {}).acceptance || {})}
        }
      } : fallback;
    }
    function dddmrMapAssetsPayload(payload = state.latest) {
      const fallback = {
        ok: true,
        code: "",
        message: "",
        manifest_path: "",
        workspace: {
          schema_version: 1,
          floor_count: 0,
          ready_floor_count: 0,
          floors: []
        },
        status: {
          ready: false,
          code: "dddmr_map_status_missing",
          frame_id: "",
          finite_points: 0
        },
        mapping: {
          host: "",
          user: "",
          start_configured: false,
          finish_configured: false,
          cancel_configured: false
        }
      };
      const value = payload && payload.dddmr_map_assets;
      return value && typeof value === "object"
        ? {
            ...fallback,
            ...value,
            workspace: {...fallback.workspace, ...(value.workspace || {})},
            status: {...fallback.status, ...(value.status || {})},
            mapping: {...fallback.mapping, ...(value.mapping || {})}
          }
        : fallback;
    }
    function navigationBackendLabel(value) {
      const text = String(value || "");
      if (text === "dddmr_3d") return "三维";
      return text || "三维";
    }
    function navigationReasonText(value) {
      const labels = {
        field_test_ready: "检查已满足",
        field_test_not_ready: "三维还未满足门禁",
        field_test_acceptance_ready: "三维验收已满足，可以开始短目标实测",
        field_test_active_task_running: "当前还有活动任务，先结束任务再做三维",
        field_test_command_mux_status_missing: "尚未收到速度仲裁器状态，先确认 command_mux 已启动",
        field_test_command_mux_status_stale: "速度仲裁器状态已过期，先确认 command_mux 心跳正常",
        field_test_command_mux_output_nonzero: "速度仲裁器仍有非零输出，先恢复零速度",
        field_test_state_unavailable: "三维验收接口不可读",
        dddmr_ready: "三维输入、三维地图和动作服务已满足门禁",
        dddmr_not_ready: "检查尚未满足",
        dddmr_bridge_status_missing: "尚未收到三维桥接状态",
        dddmr_motion_disabled: "三维运动授权未打开，当前为只读状态",
        dddmr_edge_cloud_unavailable: "edge-cloud 未就绪或已过期",
        edge_cloud_stale: "edge-cloud 数据已过期",
        edge_cloud_frame_mismatch: "edge-cloud 坐标系不是 m20pro_base_link",
        dddmr_map_unavailable: "三维静态地图缺失",
        dddmr_map_status_missing: "三维地图状态未就绪",
        dddmr_map_manifest_missing: "三维资产清单路径未配置",
        dddmr_map_manifest_invalid: "三维资产清单读取失败",
        dddmr_map_asset_missing: "三维资产文件不存在或不可读",
        dddmr_action_unavailable: "三维动作服务不可用",
        dddmr_action_type_missing: "三维action 类型未安装",
        dddmr_cmd_vel_timeout: "三维速度流超时，桥接已停车",
        dddmr_cmd_vel_start_timeout: "三维未在启动窗口内输出速度，桥接已停车",
        field_proxy_goal_accepted: "现场代理目标已接受",
        field_proxy_goal_running: "现场代理正在低速执行",
        field_proxy_rotate_to_path: "现场代理正在转向目标方向",
        field_proxy_drive: "现场代理正在低速直行",
        field_proxy_align_goal: "现场代理正在对齐目标朝向",
        field_proxy_goal_reached: "现场代理已到达目标容差",
        field_proxy_goal_succeeded: "现场代理目标完成",
        field_proxy_goal_cancelled: "现场代理目标已取消",
        field_proxy_goal_timeout: "现场代理目标超时",
        field_proxy_tf_unavailable: "现场代理缺少 map 到机身 TF",
        field_proxy_tf_ready: "现场代理 TF 可用",
        field_proxy_ready: "现场代理空闲可接目标",
        field_proxy_unavailable: "现场代理运行时不可用",
        field_proxy_goal_too_far: "现场代理拒绝过远目标",
        field_proxy_goal_frame_mismatch: "现场代理目标坐标系不匹配",
        field_proxy_goal_active: "现场代理已有活动目标",
        field_proxy_disabled: "现场代理未启用",
        field_test_task_gate_not_applicable: "当前任务不受单点限制",
        field_test_task_ready: "单点短目标满足限制",
        field_test_acceptance_not_ready: "三维验收未通过",
        field_test_selected_map_not_ready: "当前地图尚未与实时导航地图一致",
        field_test_map_relocalization_required: "当前固定地图仍要求 2101 重定位",
        field_test_localization_not_confirmed: "当前地图定位尚未确认",
        map_relocalization_required: "当前固定地图仍要求 2101 重定位",
        selected_map_missing: "当前未选中固定地图",
        selected_map_metadata_mismatch: "网页选择地图与当前空间地图元数据不一致",
        selected_map_content_mismatch: "网页选择地图与当前空间地图内容不一致",
        relocalization_pending: "正在等待本次重定位确认",
        relocalization_attempt_failed: "本次重定位失败",
        localization_not_confirmed: "定位尚未确认",
        pose_missing_or_invalid: "地图位姿缺失或无效",
        pose_stale: "地图位姿已过期",
        field_test_single_waypoint_required: "第一版只允许单点任务",
        field_test_pose_unavailable: "当前机器人位姿不新鲜，不能计算短目标",
        field_test_goal_pose_invalid: "任务点坐标无效",
        field_test_goal_distance_unknown: "无法计算任务点距离",
        field_test_goal_too_far: "任务点超过距离限制"
      };
      return labels[String(value || "")] || (value ? text(value) : "等待后端状态");
    }
    function navigationFieldTestText(fieldTest) {
      if (!fieldTest) return "未生成";
      const acceptance = fieldTest.acceptance || {};
      const runtimeLabel = fieldTest.runtime_backend === "field_proxy" ? "现场低速代理" : "";
      const modeLabel = runtimeLabel || (fieldTest.mode === "move"
        ? "三维"
        : navigationBackendLabel(fieldTest.mode || fieldTest.navigation_backend || "unknown"));
      const notes = Array.isArray(fieldTest.notes) ? fieldTest.notes : [];
      const readyCount = notes.filter(item => item && item.ready).length;
      const totalCount = notes.length;
      const ready = Object.prototype.hasOwnProperty.call(acceptance, "ready") ? !!acceptance.ready : !!fieldTest.ready;
      const reason = navigationReasonText(acceptance.reason || fieldTest.reason);
      const tail = ready ? "可直接现场点击短目标" : reason;
      return `${modeLabel} / ${tail}${totalCount ? ` / ${readyCount}/${totalCount}` : ""}`;
    }
    function navigationFieldTestAcceptanceText(acceptance) {
      if (!acceptance) return "未生成";
      const ready = Object.prototype.hasOwnProperty.call(acceptance, "ready") ? !!acceptance.ready : false;
      const reason = navigationReasonText(acceptance.reason);
      if (ready) return `可执行 / ${reason}`;
      const blocked = Array.isArray(acceptance.blocked_by) ? acceptance.blocked_by.join(" + ") : "";
      return `未就绪 / ${reason}${blocked ? ` / ${blocked}` : ""}`;
    }
    function navigationNextActionTitle(backend) {
      const fieldTest = backend.field_test || {};
      const acceptance = fieldTest.acceptance || {};
      if (acceptance.ready) return "生成近点任务";
      const code = String(navigationBlockingCode(backend) || "");
      if ([
        "field_proxy_tf_unavailable",
        "field_test_localization_not_confirmed",
        "localization_not_confirmed",
        "field_test_pose_unavailable",
        "pose_missing_or_invalid",
        "pose_stale"
      ].includes(code)) return "先完成定位";
      if ([
        "dddmr_edge_cloud_unavailable",
        "edge_cloud_stale",
        "edge_cloud_frame_mismatch"
      ].includes(code)) return "先检查 106 点云";
      if ([
        "dddmr_map_unavailable",
        "dddmr_map_manifest_missing",
        "dddmr_map_manifest_invalid",
        "dddmr_map_asset_missing"
      ].includes(code)) return "先处理 3D 地图资产";
      if ([
        "field_test_command_mux_status_missing",
        "field_test_command_mux_status_stale"
      ].includes(code)) return "先确认速度仲裁";
      if ([
        "field_test_active_task_running",
        "field_test_command_mux_output_nonzero",
        "field_proxy_goal_active"
      ].includes(code)) return "先停稳当前任务";
      return "先处理门禁";
    }
    function navigationNextActionDetail(backend) {
      const fieldTest = backend.field_test || {};
      const acceptance = fieldTest.acceptance || {};
      if (acceptance.ready) {
        return "点击“生成近点任务”，再到任务列表启动；现场保持手柄急停可用。";
      }
      const code = String(navigationBlockingCode(backend) || "");
      if ([
        "field_proxy_tf_unavailable",
        "field_test_localization_not_confirmed",
        "localization_not_confirmed",
        "field_test_pose_unavailable",
        "pose_missing_or_invalid",
        "pose_stale"
      ].includes(code)) {
        return "打开“定位”，在当前地图完成重定位；等位姿新鲜后再读取状态。";
      }
      if ([
        "dddmr_edge_cloud_unavailable",
        "edge_cloud_stale",
        "edge_cloud_frame_mismatch"
      ].includes(code)) {
        return "先检查 106 点云是否稳定发布，104 只消费处理后的空间点云。";
      }
      if ([
        "dddmr_map_unavailable",
        "dddmr_map_manifest_missing",
        "dddmr_map_manifest_invalid",
        "dddmr_map_asset_missing"
      ].includes(code)) {
        return "先在建图页登记或生成空间地图资产；第一版短测只允许明确标注的临时平面。";
      }
      if ([
        "field_test_command_mux_status_missing",
        "field_test_command_mux_status_stale"
      ].includes(code)) {
        return "先确认速度仲裁和服务正常，再读取状态；不要绕过任务链直接发速度。";
      }
      if ([
        "field_test_active_task_running",
        "field_test_command_mux_output_nonzero",
        "field_proxy_goal_active"
      ].includes(code)) {
        return "先停止当前任务并确认零速度，再重新读取状态。";
      }
      return `按详细状态处理 ${navigationReasonText(code)}，处理完再点“读取状态”。`;
    }
    function navigationBackendQuickIntroText(backend) {
      const fieldTest = backend.field_test || {};
      const acceptance = fieldTest.acceptance || {};
      if (acceptance.ready) {
        return "三维已满足门禁；实际操作仍走任务列表里的短距离单点任务。";
      }
      return `三维已切入，但门禁未满足：${navigationReasonText(acceptance.reason || fieldTest.reason || backend.reason)}`;
    }
    function navigationGnssAuxText(gnss) {
      const role = "卫星辅助，不参与运动授权";
      if (!gnss) return `未收到 / ${role}`;
      if (gnss.ready) return `可用 / ${role}`;
      const age = Number.isFinite(Number(gnss.age_s)) ? ` / ${fmtAge(Number(gnss.age_s))}前` : "";
      return `${navigationGnssReasonText(gnss.code)}${age} / ${role}`;
    }
    function navigationBackendQuickCardsHtml(backend, assets = dddmrMapAssetsPayload()) {
      const edge = backend.edge_cloud || {};
      const gnss = backend.gnss || {};
      const fieldTest = backend.field_test || {};
      const acceptance = fieldTest.acceptance || {};
      const backendLabel = navigationBackendLabel(backend.backend);
      const speedTitle = "速度链路已接通";
      const speedDetail = "速度先经过桥接和仲裁，再到机身，不能直打底盘。";
      const gateTitle = navigationFieldTestAcceptanceText(acceptance);
      const gateDetail = dddmrMapAssetsSummaryText(assets);
      return `
        <div class="navigation-quick-grid">
          <div class="navigation-quick-card">
            <span>当前模式</span>
            <strong>${escapeHtml(backendLabel)}</strong>
            <small>${escapeHtml(navigationBackendQuickIntroText(backend))}</small>
          </div>
          <div class="navigation-quick-card">
            <span>下一步</span>
            <strong>${escapeHtml(navigationNextActionTitle(backend))}</strong>
            <small>${escapeHtml(navigationNextActionDetail(backend))}</small>
          </div>
          <div class="navigation-quick-card">
            <span>速度链路</span>
            <strong>${escapeHtml(speedTitle)}</strong>
            <small>${escapeHtml(speedDetail)} ${escapeHtml(gateDetail)}</small>
          </div>
          <div class="navigation-quick-card">
            <span>卫星辅助</span>
            <strong>${escapeHtml(gnss.ready ? "可用" : navigationGnssReasonText(gnss.code))}</strong>
            <small>${escapeHtml(navigationGnssAuxText(gnss))}</small>
          </div>
        </div>`;
    }
    function dddmrFieldTestPayload(payload = state.dddmrFieldTest, livePayload = state.latest) {
      const source = payload && typeof payload === "object" ? payload : {};
      const liveBackend = livePayload && livePayload.navigation_backend && typeof livePayload.navigation_backend === "object"
        ? livePayload.navigation_backend
        : {};
      const backend = source.navigation_backend && typeof source.navigation_backend === "object"
        ? source.navigation_backend
        : liveBackend;
      const fieldTestModeSource = source.field_test_mode && typeof source.field_test_mode === "object"
        ? source.field_test_mode
        : (livePayload && livePayload.dddmr_field_test_mode && typeof livePayload.dddmr_field_test_mode === "object"
          ? livePayload.dddmr_field_test_mode
          : {});
      const fieldTestSource = source.field_test && typeof source.field_test === "object"
        ? source.field_test
        : (backend.field_test && typeof backend.field_test === "object" ? backend.field_test : {});
      const acceptanceSource = source.acceptance && typeof source.acceptance === "object"
        ? source.acceptance
        : (fieldTestSource.acceptance && typeof fieldTestSource.acceptance === "object" ? fieldTestSource.acceptance : {});
      return {
        ok: source.ok !== false,
        source_api: source.api || "/api/dddmr/field_test",
        explicit: !!payload,
        backend,
        field_test_mode: fieldTestModeSource,
        field_test: fieldTestSource,
        acceptance: acceptanceSource,
        selected_map_status: source.selected_map_status || (livePayload && livePayload.selected_map_status) || null,
        map_relocalization_required: source.map_relocalization_required || (livePayload && livePayload.map_relocalization_required) || null,
        localization_status: source.localization_status || (livePayload && livePayload.localization_status) || null,
        pose_fresh: Object.prototype.hasOwnProperty.call(source, "pose_fresh")
          ? !!source.pose_fresh
          : !!(livePayload && livePayload.pose_fresh),
        pose_age_sec: Object.prototype.hasOwnProperty.call(source, "pose_age_sec")
          ? source.pose_age_sec
          : (livePayload && livePayload.pose_age_sec),
        pose_timeout_s: Object.prototype.hasOwnProperty.call(source, "pose_timeout_s")
          ? source.pose_timeout_s
          : (livePayload && livePayload.pose_timeout_s),
        active_task: source.active_task || (livePayload && livePayload.active_task) || null,
        command_mux_status: source.command_mux_status || (livePayload && livePayload.command_mux_status) || null,
        dddmr_map_assets: source.dddmr_map_assets || dddmrMapAssetsPayload(livePayload),
        next_steps: Array.isArray(source.next_steps) ? source.next_steps : []
      };
    }
    function dddmrFieldTestTone(data) {
      const acceptance = data && data.acceptance ? data.acceptance : {};
      if (acceptance.ready) return "ok";
      return "fail";
    }
    function dddmrFieldTestStatusText(data) {
      if (!data || !data.explicit) {
        return "未单独读取三维状态；当前显示来自 /api/state 的三维快照。";
      }
      const acceptance = data.acceptance || {};
      const fieldTest = data.field_test || {};
      if (acceptance.ready) {
        return "PASS：三维已满足。可以按任务链启动短距离单点任务，全程保持手柄急停可用。";
      }
      const reason = navigationReasonText(acceptance.reason || fieldTest.reason || (data.backend && data.backend.reason));
      const blocked = Array.isArray(acceptance.blocked_by) && acceptance.blocked_by.length
        ? ` / 阻塞：${acceptance.blocked_by.join(" + ")}`
        : "";
      return `FAIL：${reason}${blocked}`;
    }
    function dddmrFieldTestNextStepAction(data) {
      const backend = data && data.backend ? data.backend : navigationBackendPayload(state.latest);
      const acceptance = data && data.acceptance ? data.acceptance : {};
      const fieldTest = data && data.field_test ? data.field_test : {};
      const reason = navigationBlockingCode(backend) || acceptance.reason || fieldTest.reason || "";
      if (acceptance.ready) {
        return {
          action: "create-task",
          label: "下一步：生成近点任务",
          title: "三维已满足门禁，直接创建近点单点任务"
        };
      }
      if ([
        "field_proxy_tf_unavailable",
        "field_test_localization_not_confirmed",
        "localization_not_confirmed",
        "field_test_pose_unavailable",
        "pose_missing_or_invalid",
        "pose_stale"
      ].includes(reason)) {
        return {
          action: "open-localization",
          label: "下一步：打开定位",
          title: "先完成当前地图重定位，再重新读取状态"
        };
      }
      if (!data || !data.explicit) {
        return {
          action: "refresh",
          label: "下一步：读取状态",
          title: "只读读取当前状态"
        };
      }
      return {
        action: "refresh",
        label: "下一步：重新读取状态",
        title: `重新读取状态：${navigationReasonText(reason)}`
      };
    }
    async function runDddmrFieldTestNextStep() {
      const data = dddmrFieldTestPayload(state.dddmrFieldTest, state.latest);
      const step = dddmrFieldTestNextStepAction(data);
      if (step.action === "open-localization") {
        setStatusPopover("localization", true);
        showOperationFeedback("下一步", "已打开定位，请完成重定位后再读取状态。");
        return;
      }
      if (step.action === "enable-dddmr") {
        await submitDddmrFieldTestMode("enable");
        return;
      }
      if (step.action === "create-task") {
        await createDddmrFieldTestTask();
        return;
      }
      await loadDddmrFieldTestAcceptance();
    }
    async function refreshDddmrAfterLocalization() {
      const backend = navigationBackendPayload(state.latest);
      if (!backend || backend.backend !== "dddmr_3d") return;
      try {
        await loadDddmrFieldTestAcceptance();
        setLog("localizeLog", "重定位已确认，状态已自动刷新；请回到建图页查看下一步。");
      } catch (err) {
        console.warn(err);
        setLog("localizeLog", "重定位已确认，但状态刷新失败；请在建图页手动读取。");
      }
    }
    function dddmrFieldTestStepsHtml(data) {
      const acceptance = data && data.acceptance ? data.acceptance : {};
      const fieldTest = data && data.field_test ? data.field_test : {};
      const notes = Array.isArray(fieldTest.notes) ? fieldTest.notes : [];
      const nextSteps = Array.isArray(data && data.next_steps) ? data.next_steps : [];
      const rows = [];
      if (nextSteps.length) {
        nextSteps.forEach((step, index) => {
          rows.push({
            ready: !!acceptance.ready,
            label: `下一步 ${index + 1}`,
            value: text(step || "")
          });
        });
      } else if (!data || !data.explicit) {
        rows.push({
          ready: false,
          neutral: true,
          label: "读取方式",
          value: "点击按钮读取当前状态；该接口只读，不会发送任务、速度、重定位或切图命令。"
        });
      } else if (!acceptance.ready) {
        rows.push({
          ready: false,
          label: "阻塞项",
          value: Array.isArray(acceptance.blocked_by) && acceptance.blocked_by.length
            ? acceptance.blocked_by.join(" + ")
            : navigationReasonText(acceptance.reason || fieldTest.reason)
        });
      }
      const selectedMapStatus = data && data.selected_map_status && typeof data.selected_map_status === "object"
        ? data.selected_map_status
        : null;
      if (selectedMapStatus) {
        rows.push({
          ready: selectedMapStatus.ready === true,
          label: "地图一致性",
          value: `${navigationReasonText(selectedMapStatus.code || (selectedMapStatus.ready ? "field_test_acceptance_ready" : ""))}${selectedMapStatus.message ? ` / ${selectedMapStatus.message}` : ""}`
        });
      }
      const mapLock = data && data.map_relocalization_required && typeof data.map_relocalization_required === "object"
        ? data.map_relocalization_required
        : null;
      rows.push({
        ready: !mapLock,
        label: "2101 重定位锁",
        value: mapLock
          ? `${mapLock.map_name || mapLock.map_id || "当前地图"} / ${mapLock.message || mapLock.reason || "需要重定位"}`
          : "已清除"
      });
      const localizationStatus = data && data.localization_status && typeof data.localization_status === "object"
        ? data.localization_status
        : null;
      if (localizationStatus) {
        rows.push({
          ready: localizationStatus.confirmed === true,
          label: "定位确认",
          value: `${navigationReasonText(localizationStatus.code || (localizationStatus.confirmed ? "field_test_acceptance_ready" : ""))}${localizationStatus.message ? ` / ${localizationStatus.message}` : ""}`
        });
      }
      rows.push({
        ready: !!(data && data.pose_fresh),
        label: "当前位姿",
        value: `fresh=${data && data.pose_fresh ? "true" : "false"} / age=${fmtNumber(Number(data && data.pose_age_sec), 2)}s / timeout=${fmtNumber(Number(data && data.pose_timeout_s), 1)}s`
      });
      notes.forEach(item => {
        if (!item || typeof item !== "object") return;
        rows.push({
          ready: !!item.ready,
          label: item.label || item.key || "检查项",
          value: `${item.value || ""}${item.message ? ` / ${item.message}` : ""}`.trim()
        });
      });
      if (!rows.length) {
        rows.push({
          ready: !!acceptance.ready,
          label: "三维",
          value: acceptance.ready ? "可执行短目标实测" : navigationFieldTestAcceptanceText(acceptance)
        });
      }
      return rows.map(item => {
        const cls = item.neutral ? "neutral" : (item.ready ? "ok" : "warn");
        const mark = item.neutral ? "·" : (item.ready ? "✓" : "!");
        return `<div class="navigation-check-row ${cls}"><span class="navigation-check-mark">${escapeHtml(mark)}</span><div><strong>${escapeHtml(item.label)}</strong><small>${escapeHtml(item.value || "")}</small></div></div>`;
      }).join("");
    }
    function renderDddmrFieldTest(payload = state.dddmrFieldTest) {
      const panel = $("dddmrFieldTestPanel");
      if (!panel) return;
      const data = dddmrFieldTestPayload(payload, state.latest);
      const tone = dddmrFieldTestTone(data);
      const tag = $("dddmrFieldTestTag");
      if (tag) {
        tag.textContent = data.acceptance && data.acceptance.ready ? "PASS" : (data.explicit ? "FAIL" : "待读取");
        tag.className = `tag ${tone}`;
      }
      const status = $("dddmrFieldTestStatus");
      if (status) {
        status.className = `navigation-runtime-message ${tone}`;
        status.textContent = dddmrFieldTestStatusText(data);
      }
      const steps = $("dddmrFieldTestSteps");
      if (steps) steps.innerHTML = dddmrFieldTestStepsHtml(data);
      const nextButton = $("dddmrNextStepBtn");
      if (nextButton) {
        const nextStep = dddmrFieldTestNextStepAction(data);
        nextButton.textContent = nextStep.label || "下一步：读取状态";
        nextButton.title = nextStep.title || "只读检查状态";
        nextButton.dataset.dddmrNextStepAction = nextStep.action || "refresh";
        nextButton.disabled = !!state.loadingDddmrFieldTest;
      }
      const taskButton = $("dddmrCreateFieldTestTaskBtn");
      if (taskButton) {
        taskButton.disabled = !(data.acceptance && data.acceptance.ready);
        taskButton.title = taskButton.disabled
          ? "通过后才能生成近点任务"
          : "只创建前方 1m 近点和单点任务，不会启动任务或发布速度";
      }
      renderDddmrFieldTestMode(state.dddmrFieldTestMode);
    }
    function dddmrFieldTestModePayload(payload = state.dddmrFieldTestMode, livePayload = state.latest) {
      const source = payload && typeof payload === "object" ? payload : {};
      const liveMode = livePayload && livePayload.dddmr_field_test_mode && typeof livePayload.dddmr_field_test_mode === "object"
        ? livePayload.dddmr_field_test_mode
        : {};
      const current = source.current && typeof source.current === "object"
        ? source.current
        : (liveMode.current && typeof liveMode.current === "object" ? liveMode.current : {});
      return {
        ok: source.ok !== false,
        api: source.api || "/api/dddmr/field_test_mode",
        explicit: !!payload,
        script: source.script || liveMode.script || "",
        available: Object.prototype.hasOwnProperty.call(source, "available")
          ? !!source.available
          : !!liveMode.available,
        current,
        available_actions: Array.isArray(source.available_actions) && source.available_actions.length
          ? source.available_actions
          : (Array.isArray(liveMode.available_actions) ? liveMode.available_actions : []),
        next_steps: Array.isArray(source.next_steps) ? source.next_steps : []
      };
    }
    function dddmrFieldTestModeTone(data) {
      const current = data && data.current ? data.current : {};
      if (current.mode === "dddmr_3d") return "ok";
      return data && data.available ? "warn" : "fail";
    }
    function dddmrFieldTestModeStatusText(data) {
      if (!data || !data.explicit) {
        return "未读取系统模式状态；当前模式将从 /api/state 自动补齐。";
      }
      const current = data.current || {};
      const script = data.script ? ` / 脚本 ${text(data.script)}` : "";
      const availability = data.available ? "可执行" : "脚本不可用";
      const backend = navigationBackendLabel(current.navigation_backend || current.mode || "未知");
      return `${availability} / 当前 ${backend}${script}`;
    }
    function renderDddmrFieldTestMode(payload = state.dddmrFieldTestMode) {
      const data = dddmrFieldTestModePayload(payload, state.latest);
      const tag = $("dddmrFieldTestModeTag");
      if (tag) {
        tag.textContent = navigationBackendLabel(data.current && data.current.mode ? data.current.mode : (data.current && data.current.navigation_backend ? data.current.navigation_backend : "unknown"));
        tag.className = `tag ${dddmrFieldTestModeTone(data)}`;
      }
      const status = $("dddmrFieldTestModeStatus");
      if (status) {
        status.className = `navigation-runtime-message ${dddmrFieldTestModeTone(data)}`;
        status.textContent = dddmrFieldTestModeStatusText(data);
      }
      const buttons = [
        ["dddmrEnableFieldTestModeBtn", "enable"]
      ];
      buttons.forEach(([id, action]) => {
        const button = $(id);
        if (!button) return;
        button.disabled = !data.available;
        button.dataset.dddmrModeAction = action;
      });
      const steps = $("dddmrFieldTestModeSteps");
      if (steps) {
        const current = data.current || {};
        const rows = [
          {
            ready: data.available,
            label: "模式脚本",
            value: data.script || "未配置"
          },
          {
            ready: !!current.ready,
            label: "当前后端",
            value: navigationBackendLabel(current.navigation_backend || current.mode || "unknown")
          },
          {
            ready: !!current.field_test_ready,
            label: "门禁",
            value: current.field_test_ready ? "已满足" : (current.field_test_reason || "未满足")
          }
        ];
        if (Array.isArray(data.next_steps) && data.next_steps.length) {
          data.next_steps.forEach((step, index) => {
            rows.push({
              ready: !!current.field_test_ready,
              label: `下一步 ${index + 1}`,
              value: String(step || "")
            });
          });
        }
        steps.innerHTML = rows.map(item => {
          const cls = item.ready ? "ok" : "warn";
          return `<div class="navigation-check-row ${cls}"><span class="navigation-check-mark">${item.ready ? "✓" : "!"}</span><div><strong>${escapeHtml(item.label)}</strong><small>${escapeHtml(item.value || "")}</small></div></div>`;
        }).join("");
      }
    }
    function dddmrFieldTestModeText(payload) {
      const data = dddmrFieldTestModePayload(payload, state.latest);
      const current = data.current || {};
      const label = navigationBackendLabel(current.mode || current.navigation_backend || "unknown");
      const script = data.available ? "脚本可执行" : "脚本缺失";
      const ready = current.field_test_ready ? "可执行" : "待验收";
      return `${label} / ${script} / ${ready}`;
    }
    function navigationBlockingCode(backend) {
      if (!backend || typeof backend !== "object") return "";
      const fieldTest = backend.field_test || {};
      const acceptance = fieldTest.acceptance || {};
      return acceptance.reason || fieldTest.reason || backend.reason || "";
    }
    function fieldProxyFieldTestActive(payload = state.latest) {
      const backend = navigationBackendPayload(payload);
      const runtime = backend.runtime || {};
      const fieldTest = backend.field_test || {};
      return backend.backend === "dddmr_3d"
        && (runtime.backend === "field_proxy" || fieldTest.runtime_backend === "field_proxy");
    }
    function fieldProxyFieldTestMaxGoal(payload = state.latest) {
      const runtime = navigationBackendPayload(payload).runtime || {};
      const value = Number(runtime.max_goal_distance_m);
      return Number.isFinite(value) && value > 0 ? value : 3.0;
    }
    function taskFieldTestGateText(gate) {
      if (!gate || typeof gate !== "object" || !gate.applies) return "";
      const maxGoal = Number.isFinite(Number(gate.max_goal_distance_m)) ? Number(gate.max_goal_distance_m).toFixed(1) : "3.0";
      if (gate.ready) {
        const distance = Number.isFinite(Number(gate.distance_m)) ? ` / 距离 ${fmtNumber(Number(gate.distance_m), 2)}m` : "";
        return `可启动：单点 ≤${maxGoal}m${distance}`;
      }
      return gate.message || navigationReasonText(gate.code);
    }
    function draftFieldTestTaskBlockText() {
      if (!fieldProxyFieldTestActive()) return "";
      const backend = navigationBackendPayload();
      const fieldTest = backend.field_test || {};
      const acceptance = fieldTest.acceptance || {};
      const maxGoal = fieldProxyFieldTestMaxGoal();
      if (!acceptance.ready) return "未通过，先读取并处理建图页检查";
      if (state.taskDraftIds.length !== 1) return `第一版只允许 ${maxGoal.toFixed(1)}m 内单点任务，请只加入一个点位`;
      const annotation = state.annotations.find(item => String(item.id) === String(state.taskDraftIds[0]));
      const goalPose = annotation && annotation.pose ? annotation.pose : null;
      const pose = freshPose();
      if (!pose) return "当前机器人位姿不新鲜，不能计算短目标；先完成定位";
      if (!goalPose || !Number.isFinite(Number(goalPose.x)) || !Number.isFinite(Number(goalPose.y))) {
        return "任务点坐标无效，请重新标点";
      }
      const distance = Math.hypot(Number(goalPose.x) - Number(pose.x), Number(goalPose.y) - Number(pose.y));
      if (!Number.isFinite(distance)) return "无法计算机器人到任务点距离，请重新定位后再试";
      if (distance > maxGoal + 0.05) {
        return `第一版只允许 ${maxGoal.toFixed(1)}m 内短目标；当前点约 ${fmtNumber(distance, 2)}m，请重新标一个近点`;
      }
      return "";
    }
    function navigationTone(backend) {
      const acceptance = backend.field_test && backend.field_test.acceptance ? backend.field_test.acceptance : null;
      if (acceptance && acceptance.ready === false && backend.ready) return "warn";
      return backend.ready ? "ok" : (backend.active ? "warn" : "fail");
    }
    function navigationCloudText(cloud) {
      if (!cloud || !cloud.ready) return `未就绪 / ${navigationReasonText(cloud && cloud.code)}`;
      const age = Number.isFinite(Number(cloud.age_s)) ? ` / ${fmtAge(Number(cloud.age_s))}前` : "";
      const frame = cloud.frame_id || "frame 未知";
      return `就绪 / ${text(cloud.finite_points)} 点 / ${frame}${age}`;
    }
    function renderUnifiedSpaceView(_payload = state.latest) {}
    function navigationGnssAuxText(gnss) {
      const role = "辅助锚点，不参与运动授权";
      if (!gnss) return `未收到 / ${role}`;
      if (gnss.ready) return `可用 / ${role}`;
      const age = Number.isFinite(Number(gnss.age_s)) ? ` / ${fmtAge(Number(gnss.age_s))}前` : "";
      return `${navigationGnssReasonText(gnss.code)}${age} / ${role}`;
    }
    function navigationGnssReasonText(value) {
      const labels = {
        gnss_adapter_disabled: "卫星辅助关闭",
        gnss_message_type_missing: "卫星辅助消息类型不可用",
        gnss_waiting: "等待卫星辅助",
        gnss_stale: "卫星辅助数据已过期",
        gnss_no_fix: "卫星辅助尚未固定",
        gnss_satellites_low: "参与定位的卫星数量不足",
        gnss_hdop_high: "水平精度因子偏高",
        gnss_anchor_ready: "卫星辅助锚点可用"
      };
      return labels[String(value || "")] || (value ? text(value) : "等待卫星辅助状态");
    }
    function renderNavigationBackend(payload = state.latest) {
      const backend = navigationBackendPayload(payload);
      renderDddmrFieldTestMode(state.dddmrFieldTestMode || backend.field_test_mode || null);
      renderDddmrFieldTest(state.dddmrFieldTest);
      renderMappingCapabilityGuide(payload, backend);
    }
    function renderMappingCapabilityGuide(payload = state.latest, backend = navigationBackendPayload(payload)) {
      const stepsBox = $("mappingCapabilitySteps");
      const status = $("mappingCapabilityStatus");
      const note = $("mappingCapabilityNote");
      if (!stepsBox || !status || !note) return;
      const dddmrAssets = state.dddmrMapAssets || null;
      const dddmrWorkspace = dddmrAssets && dddmrAssets.workspace && typeof dddmrAssets.workspace === "object"
        ? dddmrAssets.workspace
        : {};
      const dddmrAssetStatus = dddmrAssets && dddmrAssets.status && typeof dddmrAssets.status === "object"
        ? dddmrAssets.status
        : {};
      const dddmrAssetReady = Number(dddmrWorkspace.ready_floor_count || 0) > 0 || !!dddmrAssetStatus.ready;
      const dddmrReady = backend.backend === "dddmr_3d" && !!backend.ready;
      const edgeReady = !!(backend.edge_cloud && backend.edge_cloud.ready);
      const fieldTestReady = !!(backend.field_test && backend.field_test.acceptance && backend.field_test.acceptance.ready);
      const edgeText = edgeReady
        ? navigationCloudText(backend.edge_cloud)
        : navigationReasonText(backend.edge_cloud && backend.edge_cloud.code);
      const mapText = dddmrAssetReady
        ? dddmrMapAssetsSummaryText(dddmrAssets)
        : (dddmrAssets ? dddmrMapAssetsSummaryText(dddmrAssets) : "等待三维资产清单");
      const steps = [
        ["模式", dddmrReady, dddmrReady ? "已就绪" : "先完成模式切换"],
        ["点云", edgeReady, edgeText],
        ["资产", dddmrAssetReady, dddmrAssetReady ? `${dddmrWorkspace.ready_floor_count}/${dddmrWorkspace.floor_count} 个楼层就绪` : mapText],
        ["检查", fieldTestReady && dddmrReady, dddmrReady ? `${navigationFieldTestText(backend.field_test)} / ${fieldTestReady ? "已通过" : navigationReasonText(backend.reason)}` : "先完成基础检查"]
      ];
      stepsBox.innerHTML = steps.map(([label, ready, value]) => `<div class="navigation-check-row ${ready ? "ok" : "warn"}"><span class="navigation-check-mark">${ready ? "✓" : "!"}</span><span><strong>${escapeHtml(label)}</strong><small>${escapeHtml(value)}</small></span></div>`).join("");
      const finalText = dddmrReady
        ? (fieldTestReady
          ? "已就绪，可以按任务链做短目标实测。"
          : "已就绪，但门禁还差一步；先处理上面的黄项。")
        : "当前还未就绪；先完成模式、点云和资产检查。";
      status.textContent = dddmrReady ? (fieldTestReady ? "可开测" : "待门禁") : "待切换";
      status.className = `tag ${navigationTone(backend)}`;
      note.textContent = finalText;
    }
    function updateState(s) {
      preserveNewerLiveSamples(s, state.latest);
      state.latest = s;
      updateSpatialMap(s);
      state.selectedMapStatus = s.selected_map_status || null;
      state.workingMapId = s.working_map_id || null;
      state.effectiveMapId = s.effective_map_id || null;
      state.dddmrMapAssets = s.dddmr_map_assets || state.dddmrMapAssets;
      state.dddmrFieldTestMode = s.dddmr_field_test_mode || state.dddmrFieldTestMode;
      renderNavigationBackend(s);
      renderDddmrMapAssets(state.dddmrMapAssets);
      renderUnifiedSpaceView(s);
      renderLocalizationStatus(s);
      renderPreflight(s.preflight || state.preflight);
      updateMarkControls(s);
      if ($("stair")) $("stair").textContent = text(s.stair_status);
      const gaitParts = [];
      if (s.usage_mode_result) gaitParts.push(text(s.usage_mode_result));
      if (s.gait_result) gaitParts.push(text(s.gait_result));
      else if (s.gait_command) gaitParts.push(text(s.gait_command));
      const usageMode = s.navigation_status_parsed ? s.navigation_status_parsed.usage_mode : null;
      const ooa = s.navigation_status_parsed ? s.navigation_status_parsed.ooa : null;
      const usageModeText = formatUsageMode(usageMode);
      const ooaText = formatOoa(ooa);
      if (usageModeText) gaitParts.push(usageModeText);
      if (ooaText) gaitParts.push(ooaText);
      if ($("gait")) $("gait").textContent = gaitParts.length ? gaitParts.join(" / ") : "-";
      const currentPoseFresh = hasFreshPose(s);
      const currentPoseAge = poseAgeSec(s);
      if (s.pose) {
        const yawDeg = Number.isFinite(Number(s.pose.display_yaw_deg)) ? s.pose.display_yaw_deg : s.pose.yaw_deg;
        const rawYaw = fmtNumber(s.pose.yaw_deg, 0);
        const shownYaw = fmtNumber(yawDeg, 0);
        const offsetDeg = Number(s.pose.display_yaw_offset_deg || 0);
        const offsetText = Math.abs(offsetDeg) > 0.01 ? ` / 显示偏置 ${fmtNumber(offsetDeg, 0)}°` : "";
        const ageText = currentPoseAge === null || currentPoseAge === undefined ? "" : ` / ${currentPoseFresh ? "实时" : "最后"} ${fmtAge(currentPoseAge)}前`;
        if ($("pose")) $("pose").textContent = `x ${fmtNumber(s.pose.x)} / y ${fmtNumber(s.pose.y)} / 朝向 ${shownYaw}° / 原始 ${rawYaw}°${offsetText}${ageText}`;
      }
      else {
        const navPose = latestNavFeedbackPose(s);
        if (navPose) {
          const ageText = navPose.age_s === null || navPose.age_s === undefined ? "" : ` / ${fmtAge(navPose.age_s)}前`;
          if ($("pose")) $("pose").textContent = `导航反馈 x ${fmtNumber(navPose.x)} / y ${fmtNumber(navPose.y)} / 朝向 ${fmtNumber(navPose.yaw * 180 / Math.PI, 0)}°${ageText}`;
        } else {
          if ($("pose")) $("pose").textContent = poseUnavailableText(s);
        }
      }
      if (s.localization_ok === true && currentPoseFresh) $("localization").textContent = "正常";
      else if (s.localization_ok === true) $("localization").textContent = "位姿过期";
      else if (s.localization_ok === false) $("localization").textContent = "异常/未定位";
      else $("localization").textContent = "-";
      $("localization").title = (s.localization_status && s.localization_status.message) || text(s.navigation_status);
      if ($("factoryNav")) $("factoryNav").textContent = text(s.navigation_status);
      renderPoseTracker("livePoseTracker", s);
      renderRadarInspection(s.radar_inspection);
      const taskTop = $("taskTopStatus");
      const activeWaypoint = s.active_waypoint && s.active_waypoint.parsed ? s.active_waypoint.parsed : null;
      if (taskTop) {
        const transaction = s.floor_switch_transaction || null;
        const transactionText = floorSwitchTransactionText(transaction);
        const transactionState = String((transaction && transaction.state) || "").toUpperCase();
        taskTop.textContent = transactionText && ["SWITCHING_MAP", "RELOCALIZING"].includes(transactionState)
          ? transactionText
          : taskTopStatusText(s.active_task || null, activeWaypoint);
      }
      renderTeleoperation(s.teleoperation || {});
      const radarTop = $("radarTopStatus");
      if (radarTop) {
        const radarParsed = s.active_task && s.active_task.status === "running"
          ? activeRadarStatus(s.active_task, activeWaypoint)
          : (s.radar_inspection && s.radar_inspection.parsed);
        const radarStatus = radarParsed && String(radarParsed.status || radarParsed.state || "");
        radarTop.textContent = radarStatus === "running" ? "扫描中" : (radarStatus === "completed" ? "已完成" : (radarStatus === "failed" ? "异常" : (radarStatus || "等待")));
      }
      if ($("scanOverlayStatus")) {
        const mclOwned = String((s.localization_status || {}).localization_owner || "factory") === "official_mcl";
        const overlayLabel = $("scanOverlayToggleLabel");
        if (overlayLabel) overlayLabel.textContent = mclOwned ? "显示实时点云轮廓" : "显示实时激光轮廓";
        const scan = s.scan || {};
        const cloud = s.live_cloud || {};
        const points = mclOwned ? (cloud.samples || []) : (scan.points || []);
        if (points.length) {
          const age = mclOwned
            ? (cloud.last_update ? Math.max(0, (s.received_at || Date.now() / 1000) - cloud.last_update) : null)
            : (scan.last_update ? Math.max(0, s.node_time - scan.last_update) : null);
          const liveBlock = liveRobotLayerBlockedText(s);
          const mode = localizationDraftActive()
            ? "红色=待重定位预览"
            : liveBlock
            ? `${liveBlock}，暂停叠加`
            : (currentPoseFresh ? "蓝色=当前位姿" : "当前位姿未确认，暂停叠加");
          $("scanOverlayStatus").textContent = `${mclOwned ? "点云轮廓" : "激光轮廓"} ${points.length} 点 / ${mode} / ${fmtAge(age)}前`;
        } else if (!mclOwned && scan.finite_ranges) {
          $("scanOverlayStatus").textContent = "收到近场轮廓，但无可绘制数据";
        } else {
          $("scanOverlayStatus").textContent = mclOwned ? "等待实时点云轮廓数据" : "等待近场轮廓数据";
        }
      }
      if (s.battery && s.battery.primary) {
        const pack = s.battery.primary;
        const tempText = Number.isFinite(Number(pack.temperature_c)) ? ` / ${fmtNumber(Number(pack.temperature_c), 1)}℃` : "";
        $("battery").textContent = `${text(pack.level)}%`;
        $("battery").title = `${text(pack.level)}% / ${fmtNumber(Number(pack.voltage_v), 1)}V / ${fmtNumber(Number(pack.current_a), 1)}A${tempText}`;
      } else {
        $("battery").textContent = "-";
      }
      renderBatteryStatus(s);
      renderYoloWorkspace(s);
      if (
        s.relocalization_result
        && s.relocalization_result.last_update !== state.lastRelocalizationStamp
        && Date.now() > state.relocalizationApiLogUntil
      ) {
        state.lastRelocalizationStamp = s.relocalization_result.last_update;
        const loc = s.localization_status || {};
        const finalSuccess = loc.confirmed === true && !loc.map_relocalization_required;
        const logPayload = finalSuccess
          ? {
              最终结论: "重定位成功",
              判定依据: "定位已确认；地图位姿新鲜；固定地图已确认",
              更新时间: s.node_time_text
            }
          : {
              最终结论: "重定位失败",
              失败原因: loc.message || loc.code || "定位未确认",
              "2101原始回执": s.relocalization_result.raw,
              更新时间: s.node_time_text
            };
        setLog("localizeLog", logPayload);
      }
      if (s.active_task || s.active_waypoint) {
        state.activeTaskLogUntil = 0;
        const waypoint = s.active_waypoint && s.active_waypoint.parsed ? s.active_waypoint.parsed : null;
        followRobotIfNeeded(s.active_task || null);
        renderTaskExecutionFlow(s.active_task || null, waypoint || null, s.floor_switch_transaction || null);
      } else if (Date.now() > state.activeTaskLogUntil) {
        renderTaskExecutionFlow(null, null, s.floor_switch_transaction || null);
      }
      updateTaskControlButtons(s);
      const table = $("topics");
      if (table) {
        table.innerHTML = "";
        for (const [name, info] of Object.entries(s.topics || {})) {
          const tr = document.createElement("tr");
          const left = document.createElement("td");
          const right = document.createElement("td");
          left.textContent = name;
          right.textContent = info.available ? fmtAge(info.age_sec) : "无数据";
          tr.appendChild(left);
          tr.appendChild(right);
          table.appendChild(tr);
        }
      }
    }
    async function loadMaps() {
      const payload = await fetchJson("/api/maps");
      state.maps = payload.maps || [];
      state.workingMapId = payload.working_map_id || state.workingMapId || null;
      state.effectiveMapId = payload.effective_map_id || state.effectiveMapId || null;
      const selected = payload.selected_map_id || "";
      if (selected && selected !== state.selectedMapId) {
        await loadFileMap(selected);
      } else if (!selected && state.selectedMapId) {
        await loadFileMap("");
      }
      updateMarkControls();
      return payload;
    }
    const collectionPageSize = 12;
    function collectionMatches(item, query, fields) {
      const needle = String(query || "").trim().toLowerCase();
      if (!needle) return true;
      return fields.some(field => String(item && item[field] || "").toLowerCase().includes(needle));
    }
    function renderCollectionPager(id, page, total, onPage) {
      const box = $(id);
      if (!box) return;
      const pageCount = Math.max(1, Math.ceil(total / collectionPageSize));
      box.innerHTML = `
        <button type="button" data-page-offset="-1" title="上一页" ${page <= 0 ? "disabled" : ""}>←</button>
        <span>${total ? `${page + 1} / ${pageCount}` : "0 / 0"}</span>
        <button type="button" data-page-offset="1" title="下一页" ${page + 1 >= pageCount ? "disabled" : ""}>→</button>`;
      for (const button of box.querySelectorAll("[data-page-offset]")) {
        button.addEventListener("click", () => onPage(Math.max(0, Math.min(pageCount - 1, page + Number(button.dataset.pageOffset)))));
      }
    }
    async function loadAnnotations() {
      const mapId = currentAnnotationMapId();
      const payload = await fetchJson(`/api/annotations${mapId ? `?map_id=${encodeURIComponent(mapId)}` : ""}`);
      state.annotations = payload.annotations || [];
      renderAnnotations();
      renderTaskPoints();
    }
    function renderAnnotations() {
      const box = $("annotationList");
      box.innerHTML = "";
      if (!state.annotations.length) {
        if ($("annotationCount")) $("annotationCount").textContent = "0";
        renderCollectionPager("annotationPager", 0, 0, () => {});
        box.innerHTML = `<div class="small">当前地图还没有点位。</div>`;
        return;
      }
      const filtered = state.annotations.filter(item => collectionMatches(
        item,
        state.annotationQuery,
        ["label", "floor", "building", "unit", "house", "area", "room", "scan_point"]
      ));
      const pageCount = Math.max(1, Math.ceil(filtered.length / collectionPageSize));
      state.annotationPage = Math.min(state.annotationPage, pageCount - 1);
      const visible = filtered.slice(
        state.annotationPage * collectionPageSize,
        (state.annotationPage + 1) * collectionPageSize
      );
      if ($("annotationCount")) $("annotationCount").textContent = `${filtered.length} / ${state.annotations.length}`;
      renderCollectionPager("annotationPager", state.annotationPage, filtered.length, page => {
        state.annotationPage = page;
        renderAnnotations();
      });
      if (!visible.length) box.innerHTML = `<div class="small">没有匹配的点位</div>`;
      for (const item of visible) {
        const pose = item.pose || {};
        const place = [
          item.building,
          item.unit,
          item.house,
          item.area,
          item.room,
          item.scan_point,
          item.result_file_prefix ? `结果:${item.result_file_prefix}` : "",
          radarPlanText(item.radar)
        ].filter(Boolean).join(" / ");
        const el = document.createElement("div");
        el.className = "item";
        const typeLabel = annotationTypeLabel(item);
        el.innerHTML = `
          <div class="item-head">
            <span>${item.label || typeLabel || item.id}</span>
            <span class="tag">${typeLabel}</span>
          </div>
          <div class="item-meta">${item.floor || "-"} / ${typeLabel} / x ${fmtNumber(Number(pose.x))}, y ${fmtNumber(Number(pose.y))}, 朝向 ${fmtNumber(Number(pose.yaw), 2)} / 停留 ${fmtNumber(Number(item.dwell_s || 0), 1)}s</div>
          ${place ? `<div class="item-meta">${place}</div>` : ""}
          <div class="actions">
            <button data-edit-mark="${item.id}">修改</button>
            <button class="danger" data-delete-mark="${item.id}">删除</button>
          </div>
        `;
        box.appendChild(el);
      }
      for (const btn of box.querySelectorAll("[data-edit-mark]")) {
        btn.addEventListener("click", () => beginEditAnnotation(btn.dataset.editMark));
      }
      for (const btn of box.querySelectorAll("[data-delete-mark]")) {
        btn.addEventListener("click", async () => {
          try {
            await api("DELETE", `/api/annotations?id=${encodeURIComponent(btn.dataset.deleteMark)}`);
            await Promise.all([loadAnnotations(), loadFloorRoutes()]);
            draw();
            showOperationFeedback("点位已删除", "点位已从当前地图移除。任务数据会按后端合同保持一致。 ");
          } catch (err) {
            showOperationFeedback("删除点位失败", err, true);
          }
        });
      }
    }
    function setMarkEditMode(annotationId = null) {
      state.editingAnnotationId = annotationId || null;
      $("saveMarkBtn").textContent = annotationId ? "保存修改" : "保存点位";
      $("cancelEditMarkBtn").hidden = !annotationId;
    }
    function beginEditAnnotation(annotationId) {
      const item = state.annotations.find(entry => String(entry.id) === String(annotationId));
      if (!item) return;
      const pose = item.pose || {};
      setMarkEditMode(item.id);
      const supportedType = Object.prototype.hasOwnProperty.call(typeNames, item.type) ? item.type : "patrol";
      $("markType").value = supportedType;
      setFloorControlValue("markFloor", item.floor || displayedMapFloor());
      $("markLabel").value = item.label || "";
      $("markBuilding").value = item.building || "";
      $("markUnit").value = item.unit || "";
      $("markHouse").value = item.house || "";
      $("markArea").value = item.area || "";
      $("markRoom").value = item.room || "";
      $("markResultPrefix").value = item.result_file_prefix || "";
      $("markScanPoint").value = item.scan_point || "";
      $("markRadarPlan").value = radarPlanSelectValue(item.radar);
      $("markDwell").value = String(Number(item.dwell_s || 0));
      const vendor = item.vendor_navigation || {};
      $("markGait").value = String(vendor.Gait ?? defaultGaitByUiType[supportedType] ?? 12);
      $("markSpeed").value = String(vendor.Speed ?? 1);
      const z = Number.isFinite(Number(pose.z)) ? Number(pose.z) : 0.0;
      state.markDraft = {x: Number(pose.x), y: Number(pose.y), z, yaw: Number(pose.yaw || 0)};
      if ($("markZ")) $("markZ").value = z.toFixed(3);
      state.markDraftSource = "map_click";
      renderMarkPoseSummary();
      $("cursor").textContent = `正在修改 ${item.label || item.id}`;
      draw();
    }
    function renderOrderedWaypointRows(container, ids, resolveItem, onChange, emptyText) {
      container.innerHTML = "";
      for (const [index, annotationId] of ids.entries()) {
        const item = resolveItem(annotationId);
        if (!item) continue;
        const pose = item.pose || {};
        const zText = Number.isFinite(Number(pose.z)) ? ` / Z ${Number(pose.z).toFixed(2)}` : "";
        const row = document.createElement("div");
        row.className = "ordered-waypoint";
        row.innerHTML = `
          <span class="waypoint-order">${index + 1}</span>
          <span>${escapeHtml(item.floor || "-")} / ${escapeHtml(item.label || item.id)}${escapeHtml(zText)}</span>
          <span class="waypoint-actions">
            <button type="button" data-order-move="${index}:-1" title="上移" ${index === 0 ? "disabled" : ""}>↑</button>
            <button type="button" data-order-move="${index}:1" title="下移" ${index === ids.length - 1 ? "disabled" : ""}>↓</button>
            <button type="button" data-order-remove="${index}" title="移除">×</button>
          </span>`;
        container.appendChild(row);
      }
      if (!ids.length) container.innerHTML = `<div class="small">${escapeHtml(emptyText)}</div>`;
      for (const button of container.querySelectorAll("[data-order-move]")) {
        button.addEventListener("click", () => {
          const [from, offset] = button.dataset.orderMove.split(":").map(Number);
          const updated = ids.slice();
          const to = from + offset;
          [updated[from], updated[to]] = [updated[to], updated[from]];
          onChange(updated);
        });
      }
      for (const button of container.querySelectorAll("[data-order-remove]")) {
        button.addEventListener("click", () => {
          const updated = ids.slice();
          updated.splice(Number(button.dataset.orderRemove), 1);
          onChange(updated);
        });
      }
    }
    function renderTaskPoints() {
      const box = $("taskPointList");
      const available = spatialTaskAnnotations();
      state.taskDraftIds = state.taskDraftIds.filter(id => available.some(item => String(item.id) === id));
      if (!available.length) {
        if ($("taskPointCount")) $("taskPointCount").textContent = "0";
        box.textContent = "请先选择空间地图并标点";
        updateCreateTaskButton();
        return;
      }
      box.innerHTML = '<div class="floor-point-pool"></div><div class="ordered-waypoints"></div>';
      const pool = box.querySelector(".floor-point-pool");
      const draft = box.querySelector(".ordered-waypoints");
      const matching = available.filter(item => collectionMatches(
        item,
        state.taskPointQuery,
        ["label", "floor", "building", "unit", "house", "area", "room", "scan_point", "type", "manual_point_type"]
      ));
      if ($("taskPointCount")) $("taskPointCount").textContent = `${matching.length} / ${available.length}`;
      for (const item of matching.slice(0, 50)) {
        const button = document.createElement("button");
        button.type = "button";
        button.dataset.addTaskPoint = item.id;
        button.textContent = `${item.floor ? `${item.floor} / ` : ""}${item.label || item.id}`;
        button.title = `${item.floor || "-"} / ${annotationTypeLabel(item)} / ${radarPlanText(item.radar)}`;
        button.disabled = state.taskDraftIds.includes(String(item.id));
        pool.appendChild(button);
      }
      if (!matching.length) pool.innerHTML = '<span class="small">没有匹配的点位</span>';
      for (const button of pool.querySelectorAll("[data-add-task-point]")) {
        button.addEventListener("click", () => {
          state.taskDraftIds.push(String(button.dataset.addTaskPoint));
          renderTaskPoints();
        });
      }
      renderOrderedWaypointRows(
        draft,
        state.taskDraftIds,
        spatialTaskAnnotationById,
        updated => { state.taskDraftIds = updated; renderTaskPoints(); },
        "按执行顺序加入点位"
      );
      renderUnifiedTaskRouteHint(draft);
      updateCreateTaskButton();
    }
    function spatialTaskAnnotations() {
      const allFloors = multiFloorAnnotations();
      return allFloors.length ? allFloors : state.annotations;
    }
    function spatialTaskAnnotationById(annotationId) {
      return spatialTaskAnnotations().find(item => String(item.id) === String(annotationId)) || null;
    }
    function draftFloorSequenceForIds(ids) {
      const sequence = [];
      for (const annotationId of ids) {
        const annotation = spatialTaskAnnotationById(annotationId);
        const floor = String((annotation && annotation.floor) || "");
        if (floor && sequence[sequence.length - 1] !== floor) sequence.push(floor);
      }
      return sequence;
    }
    function spatialRoutePreviewForIds(ids) {
      const floors = draftFloorSequenceForIds(ids);
      const paths = [];
      for (let index = 0; index < floors.length - 1; index += 1) {
        const path = configuredFloorPath(floors[index], floors[index + 1]);
        if (!path) return {ok: false, floors, text: `缺少空间连接 ${floors[index]} -> ${floors[index + 1]}`};
        paths.push(path);
      }
      return {ok: true, floors, text: paths.length ? paths.map(path => path.join(" -> ")).join(" / ") : "单楼层任务"};
    }
    function renderUnifiedTaskRouteHint(container) {
      if (!container || !state.taskDraftIds.length) return;
      const route = spatialRoutePreviewForIds(state.taskDraftIds);
      const distinctFloors = new Set(route.floors);
      const row = document.createElement("div");
      row.className = "route-preview";
      row.textContent = distinctFloors.size >= 2
        ? `空间路径：${route.text}`
        : "空间路径：单楼层任务";
      container.appendChild(row);
    }
    function updateCreateTaskButton() {
      const btn = $("createTaskBtn");
      const box = $("taskPointList");
      if (!btn || !box) return;
      const selectedMapStatus = state.selectedMapStatus || {};
      if (selectedMapStatus.ready === false) {
        btn.disabled = true;
        btn.title = selectedMapStatus.message || "网页选择地图与当前导航地图不一致，请先切换到正确地图并重定位";
        return;
      }
      if (!spatialTaskAnnotations().length) {
        btn.disabled = true;
        btn.title = "当前空间地图还没有任务点；先标点";
        return;
      }
      if (!state.taskDraftIds.length) {
        btn.disabled = true;
        btn.title = "请按执行顺序加入空间点位";
        return;
      }
      const first = spatialTaskAnnotationById(state.taskDraftIds[0]);
      const effectiveMap = effectiveCurrentMapId() || state.selectedMapId || "";
      if (first && first.map_id && effectiveMap && String(first.map_id) !== String(effectiveMap)) {
        btn.disabled = true;
        btn.title = "任务首点必须属于当前已加载空间地图；请先切换地图或调整点位顺序";
        return;
      }
      const route = spatialRoutePreviewForIds(state.taskDraftIds);
      const distinctFloors = new Set(route.floors);
      if (distinctFloors.size >= 2 && !route.ok) {
        btn.disabled = true;
        btn.title = route.text;
        return;
      }
      const fieldTestBlock = draftFieldTestTaskBlockText();
      if (fieldTestBlock) {
        btn.disabled = true;
        btn.title = fieldTestBlock;
        return;
      }
      btn.disabled = false;
      btn.title = distinctFloors.size >= 2 ? "按当前顺序生成多楼层空间任务" : "按当前顺序生成任务";
    }
    function multiFloorAnnotations() {
      const floors = (state.multiFloor && state.multiFloor.floors) || [];
      return floors.flatMap(floor => Array.isArray(floor.annotations) ? floor.annotations : []);
    }
    function multiFloorAnnotationById(annotationId) {
      return multiFloorAnnotations().find(item => String(item.id) === String(annotationId)) || null;
    }
    function draftFloorSequence() {
      const sequence = [];
      for (const annotationId of state.crossFloorDraftIds) {
        const annotation = multiFloorAnnotationById(annotationId);
        const floor = String((annotation && annotation.floor) || "");
        if (floor && sequence[sequence.length - 1] !== floor) sequence.push(floor);
      }
      return sequence;
    }
    function configuredFloorPath(source, target) {
      if (source === target) return [source];
      const routes = ((state.multiFloor && state.multiFloor.routes) || []).filter(item => item.configured);
      const queue = [[source, [source]]];
      const visited = new Set([source]);
      while (queue.length) {
        const [floor, path] = queue.shift();
        for (const route of routes.filter(item => String(item.source_floor) === floor)) {
          const next = String(route.target_floor || "");
          if (!next || visited.has(next)) continue;
          if (next === target) return path.concat(next);
          visited.add(next);
          queue.push([next, path.concat(next)]);
        }
      }
      return null;
    }
    function crossFloorRoutePreview() {
      const floors = draftFloorSequence();
      const paths = [];
      for (let index = 0; index < floors.length - 1; index += 1) {
        const path = configuredFloorPath(floors[index], floors[index + 1]);
        if (!path) return {ok: false, floors, text: `缺少路线 ${floors[index]} -> ${floors[index + 1]}`};
        paths.push(path);
      }
      return {ok: true, floors, text: paths.length ? paths.map(path => path.join(" -> ")).join(" / ") : "至少加入两个楼层的点位"};
    }
    function selectedMappingFloors() {
      const input = $("mappingFloors");
      const floors = String((input && input.value) || "")
        .split(/[,，、;；\s]+/)
        .map(item => item.trim())
        .filter(Boolean);
      if (floors.length) return floors;
      const floor = mappingDraftFloor();
      return floor ? [floor] : [];
    }
    function setFloorControlValue(id, floor) {
      const control = $(id);
      const value = String(floor || "").trim();
      if (!control || !value) return false;
      if (!Array.from(control.options || []).some(option => option.value === value)) return false;
      control.value = value;
      return true;
    }
    function replaceFloorOptions(select, floorIds, preferred, multiple = false) {
      if (!select) return;
      const previous = multiple
        ? new Set(Array.from(select.selectedOptions || []).map(option => option.value))
        : new Set([select.value]);
      select.innerHTML = "";
      for (const floor of floorIds) {
        const option = document.createElement("option");
        option.value = floor;
        option.textContent = floor;
        option.selected = previous.has(floor) || (!previous.size && floor === preferred);
        select.appendChild(option);
      }
      if (!multiple && floorIds.length && !floorIds.includes(select.value)) {
        select.value = floorIds.includes(preferred) ? preferred : floorIds[0];
      }
    }
    function updateMappingModeUi() {
      syncMappingDraftControls();
      renderMappingFloorSteps();
    }
    function mappingStatusText(status) {
      return ({pending: "待开始", ready: "可开始", created: "已建立", mapping: "建图中", saving: "后台保存中", saved: "已归档", imported: "已归档", cancelled: "已取消", failed: "保存失败", waiting_manual: "待人工处理"})[status] || status || "待开始";
    }
    function setMappingRuntimeStatus(message, tone = "warn") {
      const box = $("mappingRuntimeStatus");
      if (!box) return;
      box.className = `compact-status ${tone || "warn"}`;
      box.textContent = message || "建图运行环境待检查";
    }
    function mappingRuntimeBlock(action, status) {
      if (!status || typeof status !== "object") return "建图运行环境状态不可读";
      if (status.configured === false) return status.message || "建图运行环境检查命令未配置";
      if (status.ok === false) return status.message || "建图运行环境检查失败";
      if (status.package_available !== true) return "三维建图运行包未安装，不能执行建图。";
      if (action === "start") {
        if (status.save_job && status.save_job.state === "running") return "三维建图正在后台保存，请等待保存完成后再开始新的建图。";
        if (status.state === "running") return "当前已经在建图，请先结束或取消当前建图。";
      }
      if (action === "finish") {
        if (status.save_job && status.save_job.state === "running") return "三维建图保存正在后台进行，请勿重复点击，等待保存结果更新。";
        if (status.mapping_health === "diverged") return status.message || "三维建图定位已发散，本次地图无法保存；请取消本次建图并重新开始。";
        if (status.state !== "running") return "三维建图当前未运行，不能结束并保存建图。";
        if (status.save_service_available !== true) return "三维建图保存服务不可用，不能结束并保存建图。";
      }
      return "";
    }
    function renderMappingRuntimeStatus(status) {
      if (!status || typeof status !== "object") {
        setMappingRuntimeStatus("建图运行环境待检查", "warn");
        return;
      }
      syncMappingInlineFromRuntime(status);
      if (status.mapping_health === "diverged") {
        setMappingRuntimeStatus(status.message || "三维建图定位已发散，本次地图无法保存；请取消本次建图并重新开始", "fail");
        return;
      }
      if (status.save_job && status.save_job.state === "running") {
        setMappingRuntimeStatus("三维建图正在后台保存归档，保存结果将自动刷新", "warn");
        return;
      }
      if (status.save_job && status.save_job.state === "failed") {
        setMappingRuntimeStatus(status.save_job.message || "三维建图后台保存失败", "fail");
        return;
      }
      const stateText = status.state && status.state !== "unknown" ? ` / ${status.state}` : "";
      if (status.package_available === true && status.save_service_available === true) {
        setMappingRuntimeStatus(`建图运行环境已就绪${stateText}`, "ok");
        return;
      }
      if (status.package_available === true) {
        setMappingRuntimeStatus(`建图运行包已安装，保存服务待启动${stateText}`, "warn");
        return;
      }
      if (status.package_available === false) {
        setMappingRuntimeStatus("三维建图运行包未安装，当前不能新建三维地图", "fail");
        return;
      }
      setMappingRuntimeStatus(status.message || "建图运行环境待检查", "warn");
    }
    async function loadMappingRuntimeStatus(force = false) {
      const assets = state.dddmrMapAssets && state.dddmrMapAssets.mapping
        ? state.dddmrMapAssets.mapping.status
        : null;
      if (!force && assets && assets.queried) {
        renderMappingRuntimeStatus(assets);
        return assets;
      }
      const status = await fetchJson("/api/dddmr/mapping/status");
      renderMappingRuntimeStatus(status);
      state.dddmrMapAssets = {
        ...(state.dddmrMapAssets || {}),
        mapping: {
          ...((state.dddmrMapAssets && state.dddmrMapAssets.mapping) || {}),
          status
        }
      };
      if (Array.isArray(status.recovered_session_ids) && status.recovered_session_ids.length) {
        await loadMultiFloorWorkspace();
      }
      return status;
    }
    const mappingProgressStages = [
      ["environment", "环境就绪"],
      ["session", "建图任务已创建"],
      ["mapping", "建图中"],
      ["saved", "建图结果已归档"]
    ];
    function rememberMappingSessionProgress(session) {
      if (!session || !session.id) return;
      const completed = new Set(state.mappingCompletedStages);
      completed.add("session");
      const status = String(session.status || "");
      if (["mapping", "saved", "imported"].includes(status)) completed.add("mapping");
      if (["saved", "imported"].includes(status)) completed.add("saved");
      state.mappingCompletedStages = Array.from(completed);
    }
    function showMappingProgress(stage, payload = null, error = false, inProgress = false) {
      // Inline progress in the mapping panel (no modal dialog): start/finish
      // must be popup-free and show live progress in the floor-steps area.
      const session = (payload && payload.session) || state.mappingSession || {};
      if (!error && !inProgress && payload && payload.session) {
        rememberMappingSessionProgress(payload.session);
      }
      if (!error && !inProgress) {
        state.mappingCompletedStages = Array.from(new Set(state.mappingCompletedStages.concat(stage)));
      }
      const box = $("mappingInlineProgress");
      if (!box) return;
      const index = Math.max(0, mappingProgressStages.findIndex(item => item[0] === stage));
      const defaults = {
        environment: "环境已确认可用",
        session: "建图任务及楼层步骤已建立",
        mapping: "建图进程已启动",
        saved: "已完成建图并把结果归档到本机"
      };
      const message = error
        ? String((payload && payload.message) || "操作失败，请检查当前阶段后重试")
        : (inProgress ? "正在处理，请稍候" : defaults[stage]);
      box.hidden = false;
      box.innerHTML = "";
      const title = document.createElement("div");
      title.className = `mapping-inline-title${error ? " fail" : ""}`;
      title.textContent = error ? "建图流程未完成" : mappingProgressStages[index][1];
      box.appendChild(title);
      const steps = document.createElement("div");
      steps.className = "operation-steps";
      for (const [stepIndex, [stepKey, label]] of mappingProgressStages.entries()) {
        const status = stepIndex === index && error
          ? "fail"
          : (stepIndex === index && inProgress
            ? "active"
            : (state.mappingCompletedStages.includes(stepKey) ? "done" : ""));
        const row = document.createElement("div");
        row.className = `operation-step ${status}`.trim();
        const mark = status === "done" ? "✓" : (status === "fail" ? "!" : String(stepIndex + 1));
        row.innerHTML = `<span class="operation-step-mark">${mark}</span><span>${escapeHtml(label)}</span>`;
        steps.appendChild(row);
      }
      box.appendChild(steps);
      const msg = document.createElement("div");
      msg.className = `operation-message${error ? " fail" : ""}`;
      msg.textContent = message;
      box.appendChild(msg);
      renderMappingFloorSteps();
    }
    function syncMappingInlineFromRuntime(status) {
      if (!status || typeof status !== "object") return;
      if (status.state === "running") {
        showMappingProgress("mapping", null, false, true);
      } else if (status.save_job && status.save_job.state === "running") {
        showMappingProgress("saved", null, false, true);
      }
    }
    function renderMappingFloorSteps() {
      const box = $("mappingFloorSteps");
      if (!box) return;
      const session = state.mappingSession;
      const draftFloors = selectedMappingFloors();
      const sessionFloors = Array.isArray(session && session.floors)
        ? session.floors.map(item => String(item || "").trim()).filter(Boolean)
        : [];
      const mode = $("mappingMode");
      const sameDraft = Boolean(
        session
        && String(session.mode || "single") === String((mode && mode.value) || "single")
        && sessionFloors.length === draftFloors.length
        && sessionFloors.every((floor, index) => floor === draftFloors[index])
      );
      if (!sameDraft) {
        box.hidden = true;
        box.replaceChildren();
        return;
      }
      box.hidden = false;
      state.mappingSession = session;
      state.sessionId = session.id || state.sessionId;
      box.innerHTML = "";
      const floorRows = (session.floor_steps || [])
        .filter(item => item && item.floor)
        .map(step => ({
          id: String(step.floor),
          mapping_step: step,
        }));
      for (const floor of floorRows) {
        const step = floor.mapping_step;
        const active = String(session.active_floor || "") === String(floor.id || "");
        const row = document.createElement("div");
        row.className = `mapping-floor-row${active ? " active" : ""}`;
        row.innerHTML = `
          <div class="floor-group-name">${escapeHtml(floor.id)}</div>
          <div>
            <div class="mapping-floor-main">
              <span>${escapeHtml(mappingStatusText(step.status))}</span>
              <button type="button" data-select-mapping-floor="${escapeHtml(floor.id)}" ${active || session.status === "mapping" ? "disabled" : ""}>${active ? "当前步骤" : "切换"}</button>
            </div>
            <div class="mapping-floor-meta">${escapeHtml(step.map_name || "-")}${step.map_id ? ` / ${escapeHtml(step.map_id)}` : ""}</div>
          </div>`;
        box.appendChild(row);
      }
      for (const button of box.querySelectorAll("[data-select-mapping-floor]")) {
        button.addEventListener("click", async () => {
          try {
            const payload = await api("POST", "/api/mapping/select_floor", {
              session_id: state.sessionId,
              floor: button.dataset.selectMappingFloor
            });
            state.mappingSession = payload.session;
            await loadMultiFloorWorkspace();
          } catch (err) { showMappingProgress("session", err, true); }
        });
      }
    }
    function mappingFlowError(err, stage) {
      const normalized = err && typeof err === "object"
        ? err
        : {ok: false, message: String(err || "建图流程失败")};
      normalized.stage = stage;
      return normalized;
    }
    function mappingSessionMatchesDraft(session) {
      if (!session || !session.id) return false;
      const floors = selectedMappingFloors();
      const project = $("projectName");
      const building = $("buildingName");
      const sessionFloors = Array.isArray(session.floors) ? session.floors.map(String) : [];
      return String(session.project_name || "") === String((project && project.value) || "").trim()
        && String(session.building || "") === String((building && building.value) || "").trim()
        && String(session.mode || "single") === "single"
        && sessionFloors.length === floors.length
        && sessionFloors.every((floor, index) => floor === floors[index]);
    }
    async function ensureMappingSession() {
      const project = $("projectName");
      const building = $("buildingName");
      const mapNameInput = $("mappingMapName");
      const floor = mappingDraftFloor();
      if (!project.value.trim() || !building.value.trim() || !floor) {
        const err = {ok: false, message: "请先填写项目名称与建筑/区域，并确认当前地图楼层已识别后再启动建图。"};
        showMappingProgress("session", err, true);
        throw mappingFlowError(err, "session");
      }
      syncMappingDraftControls(floor);
      const mode = $("mappingMode");
      const floorsInput = $("mappingFloors");
      const floors = [floor];
      showMappingProgress("environment", null, false, true);
      let environment;
      try {
        environment = await api("POST", "/api/mapping/check_environment", {});
        const runtimeStatus = await loadMappingRuntimeStatus(true);
        const block = mappingRuntimeBlock("start", runtimeStatus);
        if (block) {
          const err = {
            ok: false,
            message: block,
            code: runtimeStatus && runtimeStatus.code,
            mapping_status: runtimeStatus
          };
          showMappingProgress("environment", err, true);
          throw mappingFlowError(err, "environment");
        }
      } catch (err) {
        if (!err || !err.stage) showMappingProgress("environment", err, true);
        throw mappingFlowError(err, "environment");
      }
      showMappingProgress("environment", environment);
      const activeSession = [state.mappingSession, state.latestMappingSession]
        .find(session => session && String(session.status || "") === "mapping");
      if (activeSession) {
        const err = {ok: false, message: `${activeSession.active_floor || "当前楼层"} 正在建图，请先完成或取消当前建图任务`};
        showMappingProgress("mapping", err, true);
        throw mappingFlowError(err, "mapping");
      }
      const currentSession = state.mappingSession;
      const reusableSession = currentSession
        && mappingSessionMatchesDraft(currentSession)
        && !["saved", "imported", "cancelled", "failed"].includes(String(currentSession.status || ""))
        ? currentSession
        : null;
      if (reusableSession) {
        state.mappingSession = reusableSession;
        state.sessionId = reusableSession.id;
        showMappingProgress("session", {session: reusableSession});
        renderMappingFloorSteps();
        return reusableSession;
      }
      showMappingProgress("session", null, false, true);
      try {
        const mapName = state.mappingMapNameTouched ? mapNameInput.value.trim() : "";
        if (!state.mappingMapNameTouched) mapNameInput.value = "";
        const payload = await api("POST", "/api/mapping/session", {
          project_name: project.value,
          building: building.value,
          mode: "single",
          floors,
          active_floor: floor,
          map_name: mapName
        });
        state.sessionId = payload.session.id;
        state.mappingSession = payload.session;
        window.localStorage.setItem("m20proMappingProject", project.value.trim());
        window.localStorage.setItem("m20proMappingBuilding", building.value.trim());
        syncMappingDraftControls((payload.session.floors && payload.session.floors[0]) || payload.session.active_floor || floor);
        updateMappingModeUi();
        state.mappingMapNameTouched = false;
        showMappingProgress("session", payload);
        await loadMultiFloorWorkspace();
        return payload.session;
      } catch (err) {
        showMappingProgress("session", err, true);
        throw mappingFlowError(err, "session");
      }
    }
    function populateFloorControls(workspace) {
      const floorIds = (workspace && workspace.floors || []).map(item => String(item.id || "")).filter(Boolean);
      const mapFloor = displayedMapFloor();
      if (mapFloor && !floorIds.includes(mapFloor)) floorIds.push(mapFloor);
      if (!floorIds.length) return;
      const currentFloor = String((workspace && workspace.current_floor) || "");
      const preferred = floorIds.includes(mapFloor) ? mapFloor : (floorIds.includes(currentFloor) ? currentFloor : floorIds[0]);
      syncMappingDraftControls(state.mappingSession && state.mappingSession.active_floor
        ? String(state.mappingSession.active_floor)
        : preferred);
      if (!state.floorControlsInitialized) {
        const session = state.mappingSession || state.latestMappingSession;
        const sessionFloors = session && Array.isArray(session.floors) ? session.floors.filter(Boolean) : [];
        if (sessionFloors.length && $("mappingMode") && $("mappingFloors")) {
          syncMappingDraftControls(sessionFloors[0]);
          if (!state.mappingSession) state.mappingSession = session;
        }
      }
      updateMappingModeUi();
      replaceFloorOptions($("markFloor"), floorIds, preferred);
      setFloorControlValue("markFloor", preferred);
      state.floorControlsInitialized = true;
    }
    function renderMultiFloorSummary() {
      const box = $("multiFloorSummary");
      if (!box) return;
      const workspace = state.multiFloor;
      if (!workspace) {
        box.textContent = "正在读取空间任务配置";
        return;
      }
      const current = workspace.current_floor || "未知";
      const selectedFloor = (workspace.floors || []).find(item => item.selected);
      const selected = selectedFloor ? selectedFloor.id : "未选择";
      const status = workspace.config_available
        ? `${workspace.floor_count} 层 / ${workspace.configured_route_count} 条路线 / 就绪 ${workspace.ready_floor_count}`
        : (workspace.message || "空间任务配置不可用");
      const terrainCount = (workspace.floors || []).reduce((total, floor) => total + Number(floor.terrain_segment_count || 0), 0);
      const identityText = workspace.identity_issue_count ? ` / 未注册历史数据 ${workspace.identity_issue_count}` : "";
      box.innerHTML = `<strong>当前 ${escapeHtml(current)}</strong> / 起始地图 ${escapeHtml(selected)} / ${escapeHtml(status)} / 同层地形段 ${terrainCount}${escapeHtml(identityText)}`;
    }
    function renderCrossFloorComposer() {
      const pool = $("crossFloorPointPool");
      const draft = $("crossFloorDraft");
      const createButton = $("createCrossFloorTaskBtn");
      if (!pool || !draft || !createButton) return;
      const workspace = state.multiFloor;
      pool.innerHTML = "";
      if (!workspace || !(workspace.floors || []).length) {
        if ($("crossFloorPointCount")) $("crossFloorPointCount").textContent = "0";
        pool.innerHTML = `<div class="small">没有可用楼层或点位</div>`;
      } else {
        let remaining = 60;
        let matchCount = 0;
        for (const floor of workspace.floors) {
          const floorMatches = (floor.annotations || []).filter(item => collectionMatches(
            item,
            state.crossFloorPointQuery,
            ["label", "floor", "type", "manual_point_type"]
          ));
          matchCount += floorMatches.length;
          if (!floorMatches.length || remaining <= 0) continue;
          const row = document.createElement("div");
          row.className = "floor-group";
          const name = document.createElement("div");
          name.className = "floor-group-name";
          name.textContent = floor.id || "-";
          name.title = [
            floor.preferred_map_name ? `地图 ${floor.preferred_map_name}` : "",
            floor.historical_annotation_count ? `已排除 ${floor.historical_annotation_count} 个历史地图点位` : "",
            ...(floor.warnings || [])
          ].filter(Boolean).join(" / ");
          const points = document.createElement("div");
          points.className = "floor-group-points";
          for (const item of floorMatches.slice(0, Math.max(0, remaining))) {
            const button = document.createElement("button");
            button.type = "button";
            button.dataset.addCrossFloorPoint = item.id;
            button.textContent = item.label || item.id;
            button.title = `${floor.id} / ${item.label || item.id}`;
            button.disabled = state.crossFloorDraftIds.includes(String(item.id));
            points.appendChild(button);
          }
          remaining -= Math.min(remaining, floorMatches.length);
          row.append(name, points);
          pool.appendChild(row);
        }
        if ($("crossFloorPointCount")) $("crossFloorPointCount").textContent = String(matchCount);
        if (!matchCount) pool.innerHTML = `<div class="small">没有匹配的跨楼层点位</div>`;
      }
      for (const button of pool.querySelectorAll("[data-add-cross-floor-point]")) {
        button.addEventListener("click", () => {
          state.crossFloorDraftIds.push(String(button.dataset.addCrossFloorPoint));
          renderCrossFloorComposer();
        });
      }

      state.crossFloorDraftIds = state.crossFloorDraftIds.filter(id => multiFloorAnnotationById(id));
      renderOrderedWaypointRows(
        draft,
        state.crossFloorDraftIds,
        multiFloorAnnotationById,
        updated => { state.crossFloorDraftIds = updated; renderCrossFloorComposer(); },
        "从各楼层依次加入任务点"
      );
      const route = crossFloorRoutePreview();
      const routeLine = document.createElement("div");
      routeLine.className = "route-preview";
      routeLine.textContent = `楼层路径：${route.text}`;
      draft.appendChild(routeLine);
      const first = multiFloorAnnotationById(state.crossFloorDraftIds[0]);
      const selectedMapId = String((workspace && workspace.selected_map_id) || state.selectedMapId || "");
      const distinctFloors = new Set(route.floors);
      const startMapReady = !!first && String(first.map_id || "") === selectedMapId;
      const localizationReady = !state.selectedMapStatus || state.selectedMapStatus.ready !== false;
      createButton.disabled = !(route.ok && distinctFloors.size >= 2 && startMapReady && localizationReady);
      createButton.title = !startMapReady
        ? "顺序中的首点必须属于当前已加载地图"
        : (!route.ok
          ? route.text
          : (distinctFloors.size < 2
            ? "至少选择两个楼层"
            : (!localizationReady
              ? ((state.selectedMapStatus && state.selectedMapStatus.message) || "当前地图尚未完成重定位")
              : "生成跨楼层任务")));
    }
    async function loadMultiFloorWorkspace() {
      const payload = await fetchJson("/api/multi_floor");
      state.multiFloor = payload;
      state.latestMappingSession = payload.latest_mapping_session || null;
      if (
        state.latestMappingSession
        && (!state.mappingSession
          || (state.mappingSession.id === state.latestMappingSession.id
            && state.mappingSession.status === "mapping"
            && state.latestMappingSession.status !== "mapping"))
      ) {
        state.mappingSession = state.latestMappingSession;
      }
      state.lastMultiFloorRefreshAt = Date.now();
      populateFloorControls(payload);
      if (state.mappingSession && state.mappingSession.id) {
        state.sessionId = state.mappingSession.id;
      }
      renderMultiFloorSummary();
      renderCrossFloorComposer();
      renderMappingFloorSteps();
      return payload;
    }

    function floorRouteCandidate(id) {
      return (state.floorRoutes.candidates || []).find(item => String(item.id) === String(id)) || null;
    }

    function replaceFloorRouteOptions(select, candidates, placeholder) {
      if (!select) return;
      const previous = select.value;
      select.innerHTML = "";
      const empty = document.createElement("option");
      empty.value = "";
      empty.textContent = placeholder;
      select.appendChild(empty);
      for (const item of candidates) {
        const option = document.createElement("option");
        option.value = item.id;
        option.textContent = `${item.floor} / ${item.label}`;
        select.appendChild(option);
      }
      select.value = candidates.some(item => String(item.id) === previous) ? previous : (candidates.length === 1 ? candidates[0].id : "");
    }

    function renderFloorRouteWorkspace() {
      const entrySelect = $("floorRouteEntry");
      const sourceSelect = $("floorRouteSourcePlatform");
      const targetSelect = $("floorRouteTargetPlatform");
      const postExitSelect = $("floorRoutePostExit");
      const preview = $("floorRoutePreview");
      const saveButton = $("saveFloorRouteBtn");
      const list = $("floorRouteList");
      if (!entrySelect || !sourceSelect || !targetSelect || !postExitSelect || !preview || !saveButton || !list) return;
      const candidates = state.floorRoutes.candidates || [];
      const entries = candidates.filter(item => item.type === "stair_entry");
      replaceFloorRouteOptions(entrySelect, entries, entries.length ? "选择爬楼梯点" : "请先标注爬楼梯点");
      const entry = floorRouteCandidate(entrySelect.value);
      const sourceSwitches = candidates.filter(item => item.type === "stair_switch"
        && entry && item.floor === entry.floor && item.map_id === entry.map_id);
      replaceFloorRouteOptions(sourceSelect, sourceSwitches, sourceSwitches.length ? "选择起始层切换点" : "缺少同地图切换点");
      const targetSwitches = candidates.filter(item => item.type === "stair_switch"
        && entry && item.floor !== entry.floor);
      replaceFloorRouteOptions(targetSelect, targetSwitches, targetSwitches.length ? "选择目标层切换点" : "缺少目标层切换点");
      const targetPlatform = floorRouteCandidate(targetSelect.value);
      const exits = candidates.filter(item => item.type === "stair_exit"
        && targetPlatform && item.floor === targetPlatform.floor && item.map_id === targetPlatform.map_id);
      replaceFloorRouteOptions(postExitSelect, exits, exits.length ? "选择目标层出楼梯点" : "缺少目标层出口点");

      const sourcePlatform = floorRouteCandidate(sourceSelect.value);
      const postExit = floorRouteCandidate(postExitSelect.value);
      const complete = !!(entry && sourcePlatform && targetPlatform && postExit);
      saveButton.disabled = !complete;
      preview.textContent = complete
        ? `${entry.floor} / ${entry.label} → ${sourcePlatform.label} → 切换 ${targetPlatform.floor} / ${targetPlatform.label} → ${postExit.label}`
        : "依次选择起始层入口、两侧切换点和目标层出口";
      list.innerHTML = "";
      const mapNames = new Map((state.floorRoutes.maps || []).map(item => [String(item.id), item.name || item.id]));
      for (const route of state.floorRoutes.routes || []) {
        const item = document.createElement("div");
        item.className = "item";
        item.innerHTML = `
          <div class="item-head"><span>${escapeHtml(route.name || route.id)}</span><span class="tag">${route.direction === "down" ? "下楼" : "上楼"}</span></div>
          <div class="item-meta">${escapeHtml(route.source_floor)} → ${escapeHtml(route.target_floor)} / ${escapeHtml(mapNames.get(String(route.source_map_id)) || route.source_map_id)} → ${escapeHtml(mapNames.get(String(route.target_map_id)) || route.target_map_id)}</div>
          <div class="actions"><button class="danger" data-delete-floor-route="${escapeHtml(route.id)}">删除路线</button></div>`;
        list.appendChild(item);
      }
      if (!(state.floorRoutes.routes || []).length) list.innerHTML = '<div class="small">尚未配置有向跨楼层路线</div>';
      for (const button of list.querySelectorAll("[data-delete-floor-route]")) {
        button.addEventListener("click", async () => {
          if (!window.confirm("删除这条跨楼层路线？相关点位和地图不会删除。")) return;
          try {
            await api("POST", "/api/floor_routes/delete", {id: button.dataset.deleteFloorRoute});
            await Promise.all([loadFloorRoutes(), loadMultiFloorWorkspace()]);
          } catch (err) { showOperationFeedback("删除路线失败", err, true); }
        });
      }
    }

    async function loadFloorRoutes() {
      state.floorRoutes = await fetchJson("/api/floor_routes");
      renderFloorRouteWorkspace();
      return state.floorRoutes;
    }
    async function loadTasks() {
      if (state.loadingTasks) return;
      state.loadingTasks = true;
      try {
        const effectiveMapId = effectiveCurrentMapId();
        const query = effectiveMapId ? `?map_id=${encodeURIComponent(effectiveMapId)}` : "";
        const payload = await fetchJson(`/api/tasks${query}`);
        state.lastTasksRefreshAt = Date.now();
        state.lastTasksPayload = payload;
        if (payload.selected_map_status) state.selectedMapStatus = payload.selected_map_status;
        state.tasks = payload.tasks || [];
        if (Date.now() - state.lastMultiFloorRefreshAt > 10000) loadMultiFloorWorkspace().catch(console.warn);
        const box = $("taskList");
        box.innerHTML = "";
        if (!state.tasks.length) {
          if ($("taskCount")) $("taskCount").textContent = "0";
          renderCollectionPager("taskPager", 0, 0, () => {});
          return;
        }
        const currentMapTasks = state.tasks.filter(task => taskBelongsToSelectedMap(task));
        if (!currentMapTasks.length) {
          if ($("taskCount")) $("taskCount").textContent = "0";
          renderCollectionPager("taskPager", 0, 0, () => {});
          return;
        }
        const filteredTasks = currentMapTasks.filter(task => {
          if (collectionMatches(task, state.taskQuery, ["name", "id", "status", "created_at"])) return true;
          return (task.waypoints || []).some(point => collectionMatches(point, state.taskQuery, ["label", "floor", "room", "scan_point"]));
        });
        const taskPageCount = Math.max(1, Math.ceil(filteredTasks.length / collectionPageSize));
        state.taskPage = Math.min(state.taskPage, taskPageCount - 1);
        const visibleTasks = filteredTasks.slice(
          state.taskPage * collectionPageSize,
          (state.taskPage + 1) * collectionPageSize
        );
        if ($("taskCount")) $("taskCount").textContent = `${filteredTasks.length} / ${currentMapTasks.length}`;
        renderCollectionPager("taskPager", state.taskPage, filteredTasks.length, page => {
          state.taskPage = page;
          loadTasks().catch(console.warn);
        });
        if (currentMapTasks.length && !visibleTasks.length) box.innerHTML = '<div class="small">没有匹配的任务</div>';
        for (const task of visibleTasks) {
          const activeTask = payload.active_task && payload.active_task.status === "running" ? payload.active_task : null;
          const active = !!activeTask;
          const isRunning = !!(activeTask && activeTask.task_id === task.id);
          const taskStatus = normalizedTaskStatus(task.status);
          const statusAllowsStart = taskStatusAllowsStart(taskStatus);
          const mapMismatchText = taskMapMismatchText(task);
          const fieldTestGate = task.field_test_task_gate && typeof task.field_test_task_gate === "object"
            ? task.field_test_task_gate
            : {};
          const fieldTestGateText = taskFieldTestGateText(fieldTestGate);
          const fieldTestBlockText = fieldTestGate.applies && !fieldTestGate.ready ? fieldTestGateText : "";
          const canStart = !active && !isRunning && statusAllowsStart && !mapMismatchText && !fieldTestBlockText;
          const canDelete = !isRunning && !(payload.active_task && payload.active_task.task_id === task.id);
          const statusBlockText = taskStatusBlockText(taskStatus);
          const taskNote = mapMismatchText || statusBlockText || fieldTestBlockText || "任务接口已通过；自检和现场确认不在任务按钮重复检查";
          const startLabel = isRunning
            ? "执行中"
            : (active
              ? "先停止当前任务"
              : (mapMismatchText
                ? "旧地图任务"
                : (fieldTestBlockText ? "门禁阻塞" : taskStartLabelForStatus(taskStatus))));
          const fieldTestGateHtml = fieldTestGate.applies
            ? `<div class="item-meta">${escapeHtml(fieldTestGateText || "三维任务门禁已读取")}</div>`
            : "";
          const displayStatus = taskDisplayStatus(taskStatus, task.multi_floor, mapMismatchText);
          const waypointDetails = Array.isArray(task.waypoints) ? task.waypoints : [];
          const waypointOrderText = waypointDetails.length
            ? waypointDetails.map((point, index) => taskWaypointText(point, index)).join(" → ")
            : "无点位";
          const firstWaypoint = waypointDetails.length ? waypointDetails[0] : null;
          const firstPose = firstWaypoint && firstWaypoint.pose ? firstWaypoint.pose : {};
          const firstTargetText = firstWaypoint
            ? `首点：${firstWaypoint.floor || "-"} / ${firstWaypoint.label || firstWaypoint.id || "-"} / x ${fmtNumber(Number(firstPose.x), 2)}, y ${fmtNumber(Number(firstPose.y), 2)}, 朝向 ${fmtNumber(Number(firstPose.yaw), 2)}`
            : "首点：-";
          const radarResultsHtml = radarTaskResultsHtml(task);
          const el = document.createElement("div");
          el.className = "item";
          el.innerHTML = `
            <div class="item-head"><span>${task.name || task.id}</span><span class="tag">${displayStatus}</span></div>
            <div class="item-meta">${(task.annotation_ids || []).length} 个点 / ${task.created_at || ""}${task.updated_at ? ` / 更新 ${task.updated_at}` : ""}</div>
            <div class="item-meta">${firstTargetText}</div>
            <details class="item-details">
              <summary>点位顺序（${waypointDetails.length}）</summary>
              <div class="item-meta">${waypointOrderText}</div>
              ${fieldTestGateHtml}
              <div class="item-meta">${taskNote}</div>
              ${radarResultsHtml}
            </details>
            <div class="actions">
              <button class="primary" data-start-task="${task.id}" title="${taskNote}" ${canStart ? "" : "disabled"}>${startLabel}</button>
              <button data-rename-task="${task.id}">改名</button>
              <button class="danger" data-delete-task="${task.id}" ${canDelete ? "" : "disabled"}>删除</button>
            </div>
          `;
          box.appendChild(el);
        }
        for (const btn of box.querySelectorAll("[data-start-task]")) {
          btn.addEventListener("click", async () => {
            btn.disabled = true;
            btn.textContent = "确认中...";
            try {
              const task = state.tasks.find(item => item.id === btn.dataset.startTask);
              if (!task) throw {message: "任务列表已变化，请刷新后重试"};
              const taskNote = taskStatusBlockText(normalizedTaskStatus(task.status)) || "任务接口已通过；自检和现场确认不在任务按钮重复检查";
              if (!window.confirm(taskStartConfirmText(task, taskNote))) return;
              btn.textContent = "启动中...";
              const payload = await api("POST", "/api/tasks/start", taskStartRequest(task));
              state.activeTaskLogUntil = Date.now() + 20000;
              renderTaskExecutionFlow(payload.active_task || null, null);
              await loadTasks();
            } catch (err) {
              state.activeTaskLogUntil = Date.now() + 30000;
              showOperationFeedback("任务启动失败", err, true);
            } finally {
              await loadTasks();
            }
          });
        }
        for (const btn of box.querySelectorAll("[data-radar-artifact]")) {
          btn.addEventListener("click", async () => {
            try {
              await recordRadarArtifact(btn.dataset.taskId, btn.dataset.radarArtifact);
            } catch (err) { setLog("activeTask", err); }
          });
        }
        for (const btn of box.querySelectorAll("[data-radar-manual]")) {
          btn.addEventListener("click", async () => {
            try {
              await saveRadarManualMeasurement(btn.dataset.taskId, btn.dataset.radarManual);
            } catch (err) { setLog("activeTask", err); }
          });
        }
        for (const btn of box.querySelectorAll("[data-rename-task]")) {
          btn.addEventListener("click", async () => {
            const task = state.tasks.find(item => item.id === btn.dataset.renameTask);
            if (!task) return;
            const name = window.prompt("请输入新的任务名称", task.name || "");
            if (name === null) return;
            const trimmed = name.trim();
            if (!trimmed) return;
            try {
              await api("POST", "/api/tasks/update", {task_id: task.id, name: trimmed});
              await loadTasks();
              showOperationFeedback("任务已更新", `任务名称已改为“${trimmed}”`);
            } catch (err) { setLog("activeTask", err); }
          });
        }
        for (const btn of box.querySelectorAll("[data-delete-task]")) {
          btn.addEventListener("click", async () => {
            const task = state.tasks.find(item => item.id === btn.dataset.deleteTask);
            if (!task) return;
            if (!window.confirm(`确认删除任务“${task.name || task.id}”？点位不会被删除。`)) return;
            try {
              await api("DELETE", `/api/tasks?id=${encodeURIComponent(task.id)}`);
              await loadTasks();
              showOperationFeedback("任务已删除", `已删除“${task.name || task.id}”，点位数据仍保留。`);
            } catch (err) { setLog("activeTask", err); }
          });
        }
      } catch (err) {
        showOperationFeedback("任务列表加载失败", err, true);
        console.warn(err);
      } finally {
        state.loadingTasks = false;
      }
    }
    async function mainLoop() {
      const dot = $("statusDot");
      const label = $("statusText");
      try {
        const tabName = activeTabName();
        const stateUrl = ["live", "detect", "more"].includes(tabName) ? "/api/state" : "/api/state?debug=0";
        const s = await fetchJson(stateUrl);
        updateState(s);
        if (Date.now() - state.lastDddmrMapAssetsRefreshAt > 4000) {
          loadDddmrMapAssets().catch(console.warn);
        }
        dot.className = "dot ok";
        label.textContent = "已连接";
        draw();
        if (["tasks", "work"].includes(activeTabName()) && Date.now() - state.lastTasksRefreshAt > 3000) {
          loadTasks().catch(console.warn);
        }
        if (["live", "detect"].includes(tabName) && Date.now() - state.lastRadarResultsRefreshAt > 10000) {
          loadRadarResults().catch(console.warn);
        }
        if ($("recordingStatus") && Date.now() - state.lastRecordingRefreshAt > 2000) {
          loadRecordingStatus().catch(console.warn);
        }
      } catch (err) {
        dot.className = "dot warn";
        label.textContent = "等待服务";
        console.warn(err);
      } finally {
        setTimeout(mainLoop, 1500);
      }
    }
    function sampleUpdateTime(sample) {
      const value = sample && Number(sample.last_update);
      return Number.isFinite(value) ? value : -1;
    }
    function preserveNewerLiveSamples(target, current) {
      if (!target || !current) return target;
      for (const key of ["pose", "scan", "path", "local_path", "active_waypoint"]) {
        if (sampleUpdateTime(current[key]) > sampleUpdateTime(target[key])) target[key] = current[key];
      }
      return target;
    }
    function mergeLiveState(live) {
      if (!live || !state.latest) return;
      const merged = {...state.latest};
      for (const key of ["pose", "scan", "path", "local_path", "active_waypoint"]) {
        if (live[key] && sampleUpdateTime(live[key]) >= sampleUpdateTime(merged[key])) merged[key] = live[key];
      }
      for (const key of ["floor", "localization_ok", "map_version", "node_time", "pose_age_sec", "pose_timeout_s", "pose_fresh"]) {
        if (live[key] !== undefined) merged[key] = live[key];
      }
      state.latest = merged;
    }
    function liveStateUrl() {
      const pathVersion = state.latest && state.latest.path ? Number(state.latest.path.version) : -1;
      const localPathVersion = state.latest && state.latest.local_path ? Number(state.latest.local_path.version) : -1;
      const query = new URLSearchParams({
        path_version: Number.isFinite(pathVersion) ? String(pathVersion) : "-1",
        local_path_version: Number.isFinite(localPathVersion) ? String(localPathVersion) : "-1"
      });
      return `/api/live?${query.toString()}`;
    }
    async function liveLoop() {
      if (!document.hidden && !state.liveRequestInFlight) {
        state.liveRequestInFlight = true;
        try {
          mergeLiveState(await fetchJson(liveStateUrl()));
          draw();
        } catch (err) {
          console.warn(err);
        } finally {
          state.liveRequestInFlight = false;
        }
      }
      setTimeout(liveLoop, 125);
    }
    function mergeInspectionState(live) {
      if (!live) return;
      state.latest = {
        ...(state.latest || {}),
        detections: live.detections ?? null,
        inspection_status: live.inspection_status ?? null,
        inspection_control: live.inspection_control || {}
      };
      renderYoloWorkspace(state.latest);
    }
    async function yoloLiveLoop() {
      const yoloEnabled = Boolean(
        state.yoloControlBusy
        || (state.latest && state.latest.inspection_control && state.latest.inspection_control.enabled)
        || (state.latest && topicPayload(state.latest.inspection_status)?.enabled === true)
      );
      const shouldPoll = !document.hidden && cameraViewers.front.active;
      if (shouldPoll && !state.yoloLiveRequestInFlight) {
        state.yoloLiveRequestInFlight = true;
        try {
          mergeInspectionState(await fetchJson("/api/inspection/state"));
        } catch (err) {
          console.warn(err);
        } finally {
          state.yoloLiveRequestInFlight = false;
        }
      }
      setTimeout(yoloLiveLoop, yoloEnabled ? 200 : 750);
    }
    for (const btn of document.querySelectorAll("button.tab")) {
      btn.addEventListener("click", () => {
        setStatusPopover("", false);
        document.querySelectorAll("button.tab").forEach(item => item.classList.remove("active"));
        document.querySelectorAll(".panel").forEach(item => item.classList.remove("active"));
        btn.classList.add("active");
        $(`tab-${btn.dataset.tab}`).classList.add("active");
        if (["live", "detect"].includes(btn.dataset.tab)) loadRadarResults().catch(console.warn);
        updatePointerModeUi();
        draw();
      });
    }
    canvas.addEventListener("pointerdown", (evt) => {
      if (state.view.panMode || evt.button === 1 || evt.button === 2 || evt.shiftKey || evt.altKey) {
        evt.preventDefault();
        state.panPointer = {
          id: evt.pointerId,
          x: evt.clientX,
          y: evt.clientY,
          panX: state.view.panX,
          panY: state.view.panY
        };
        canvas.classList.add("panning");
        canvas.setPointerCapture(evt.pointerId);
        return;
      }
      if (effectiveMapViewMode() === "3d" && !activePointerMode()) {
        evt.preventDefault();
        state.rotatePointer = {
          id: evt.pointerId,
          x: evt.clientX,
          y: evt.clientY,
          yaw: state.view.yaw,
          pitch: state.view.pitch
        };
        canvas.classList.add("orbiting");
        canvas.setPointerCapture(evt.pointerId);
        $("cursor").textContent = "PCD 点云视角：拖动旋转";
        return;
      }
      if (effectiveMapViewMode() === "3d" && activePointerMode() === "mark") {
        const picked = pick3dMarkPoint(evt.clientX, evt.clientY);
        if (picked) {
          evt.preventDefault();
          setMarkDraft(
            {x: picked[0], y: picked[1], z: picked[2], yaw: currentMarkYaw()},
            `拾取点云 x ${picked[0].toFixed(2)} / y ${picked[1].toFixed(2)} / z ${picked[2].toFixed(2)}（3D 点击拾取；切俯视拖动可设朝向）`
          );
        } else {
          $("cursor").textContent = "未点中点云：请点击靠近点云的像素";
        }
        return;
      }
      const p = canvasToWorld(evt.clientX, evt.clientY);
      if (!p) return;
      const mode = activePointerMode();
      if (!mode) return;
      evt.preventDefault();
      state.markPointer = {id: evt.pointerId, start: p, moved: false, mode};
      canvas.setPointerCapture(evt.pointerId);
      if (state.markPointer.mode === "localize") {
        setLocalizeDraft(
          {x: p.x, y: p.y, yaw: currentLocalizeYaw()},
          `定位 x ${p.x.toFixed(3)} / y ${p.y.toFixed(3)} / 拖动设置朝向`
        );
      } else {
        const clickX = p.x;
        const clickY = p.y;
        pickStandingZ(clickX, clickY, effectiveSliceZ(state.spatialMap)).then(pickedZ => {
          const z = pickedZ === null ? currentMarkZ(0.0) : pickedZ;
          setMarkDraft(
            {x: clickX, y: clickY, z, yaw: currentMarkYaw()},
            `x ${clickX.toFixed(3)} / y ${clickY.toFixed(3)} / z ${Number(z).toFixed(2)}（全分辨率站立面）/ 拖动设置朝向`
          );
        });
      }
    });
    canvas.addEventListener("pointermove", (evt) => {
      if (state.panPointer && state.panPointer.id === evt.pointerId) {
        evt.preventDefault();
        state.view.panX = state.panPointer.panX + (evt.clientX - state.panPointer.x);
        state.view.panY = state.panPointer.panY + (evt.clientY - state.panPointer.y);
        clampView();
        draw();
        $("cursor").textContent = `地图缩放 ${Math.round(state.view.zoom * 100)}%`;
        return;
      }
      if (state.rotatePointer && state.rotatePointer.id === evt.pointerId) {
        evt.preventDefault();
        const dx = evt.clientX - state.rotatePointer.x;
        const dy = evt.clientY - state.rotatePointer.y;
        state.view.yaw = state.rotatePointer.yaw + dx * 0.008;
        // 与通用轨道控制一致：下拖=抬高视点趋向俯视，上拖=视点下沉、经水平继续到仰视。
        state.view.pitch = clamp3dPitch(state.rotatePointer.pitch - dy * 0.005);
        draw();
        $("cursor").textContent = `PCD 点云视角：yaw ${state.view.yaw.toFixed(2)} / pitch ${state.view.pitch.toFixed(2)}`;
        return;
      }
      const p = canvasToWorld(evt.clientX, evt.clientY);
      if (!p) {
        if (effectiveMapViewMode() === "3d") $("cursor").textContent = "PCD 点云视角：拖拽旋转，滚轮缩放";
        return;
      }
      if (!state.markPointer || state.markPointer.id !== evt.pointerId) {
        $("cursor").textContent = `x ${p.x.toFixed(3)} / y ${p.y.toFixed(3)}`;
        return;
      }
      evt.preventDefault();
      const start = state.markPointer.start;
      const distance = Math.hypot(p.x - start.x, p.y - start.y);
      const yaw = distance > 0.03 ? Math.atan2(p.y - start.y, p.x - start.x) : (
        state.markPointer.mode === "localize" ? currentLocalizeYaw() : currentMarkYaw()
      );
      state.markPointer.moved = state.markPointer.moved || distance > 0.03;
      if (state.markPointer.mode === "localize") {
        setLocalizeDraft(
          {x: start.x, y: start.y, yaw},
          `定位 x ${start.x.toFixed(3)} / y ${start.y.toFixed(3)} / 朝向 ${normalizeYaw(yaw).toFixed(3)} rad`
        );
      } else {
        setMarkDraft(
          {x: start.x, y: start.y, yaw},
          `x ${start.x.toFixed(3)} / y ${start.y.toFixed(3)} / 朝向 ${normalizeYaw(yaw).toFixed(3)} rad`
        );
      }
    });
    function finishMarkPointer(evt) {
      if (state.panPointer && state.panPointer.id === evt.pointerId) {
        evt.preventDefault();
        if (canvas.hasPointerCapture(evt.pointerId)) canvas.releasePointerCapture(evt.pointerId);
        state.panPointer = null;
        canvas.classList.remove("panning");
        return;
      }
      if (state.rotatePointer && state.rotatePointer.id === evt.pointerId) {
        evt.preventDefault();
        if (canvas.hasPointerCapture(evt.pointerId)) canvas.releasePointerCapture(evt.pointerId);
        state.rotatePointer = null;
        canvas.classList.remove("orbiting");
        $("cursor").textContent = "PCD 点云视角：拖拽旋转，滚轮缩放，Shift/右键平移";
        return;
      }
      if (!state.markPointer || state.markPointer.id !== evt.pointerId) return;
      evt.preventDefault();
      if (canvas.hasPointerCapture(evt.pointerId)) canvas.releasePointerCapture(evt.pointerId);
      const mode = state.markPointer.mode;
      const pose = mode === "localize" ? state.localizeDraft : state.markDraft;
      state.markPointer = null;
      if (pose) {
        $("cursor").textContent = `${mode === "localize" ? "待重定位" : "待保存"} x ${pose.x.toFixed(3)} / y ${pose.y.toFixed(3)} / 朝向 ${pose.yaw.toFixed(3)} rad`;
      }
    }
    canvas.addEventListener("pointerup", finishMarkPointer);
    canvas.addEventListener("pointercancel", finishMarkPointer);
    canvas.addEventListener("contextmenu", (evt) => evt.preventDefault());
    canvas.addEventListener("wheel", (evt) => {
      evt.preventDefault();
      if (!state.spatialMap) return;
      const factor = Math.exp(-evt.deltaY * 0.0012);
      if (effectiveMapViewMode() === "3d") {
        state.view.zoom = clampZoom(state.view.zoom * factor);
        clampView();
        draw();
        return;
      }
      setZoomAt(evt.clientX, evt.clientY, state.view.zoom * factor);
    }, {passive: false});
    $("zoomOutBtn").addEventListener("click", () => zoomBy(1 / 1.25));
    $("zoomInBtn").addEventListener("click", () => zoomBy(1.25));
    $("mapViewModeBtn").addEventListener("click", () => {
      state.mapViewMode = state.mapViewMode === "3d" ? "topdown" : "3d";
      if (state.mapViewMode === "3d") {
        state.view.panMode = false;
        $("panModeBtn").classList.remove("active-tool");
      }
      updateMapModeUi();
      updateLiveSpatialMapHeader();
      draw();
    });
    const sliceSlider = $("sliceZSlider");
    if (sliceSlider) {
      sliceSlider.addEventListener("input", () => {
        state.view.sliceZ = Number(sliceSlider.value);
        draw();
      });
    }
    $("sliceUpBtn").addEventListener("click", () => {
      const map = state.spatialMap;
      if (!map) return;
      const z = effectiveSliceZ(map);
      const next = (map.layers || [])
        .filter(layer => layer.z > z + 0.2)
        .sort((a, b) => a.z - b.z)[0];
      if (next) state.view.sliceZ = next.z;
      draw();
    });
    $("sliceDownBtn").addEventListener("click", () => {
      const map = state.spatialMap;
      if (!map) return;
      const z = effectiveSliceZ(map);
      const next = (map.layers || [])
        .filter(layer => layer.z < z - 0.2)
        .sort((a, b) => b.z - a.z)[0];
      if (next) state.view.sliceZ = next.z;
      draw();
    });
    $("sliceAutoBtn").addEventListener("click", () => {
      state.view.sliceZ = null;
      draw();
    });
    $("panModeBtn").addEventListener("click", () => {
      state.view.panMode = !state.view.panMode;
      $("panModeBtn").classList.toggle("active-tool", state.view.panMode);
      if (state.view.panMode) {
        state.followRobot = false;
        $("followRobotBtn").classList.remove("active-tool");
      }
      $("cursor").textContent = state.view.panMode ? "平移模式" : "拖拽空间视图取点和朝向";
    });
    $("fitMapBtn").addEventListener("click", () => {
      resetMapView(true);
    });
    $("centerRobotBtn").addEventListener("click", () => {
      const mismatch = selectedMapFloorMismatchText();
      if (mismatch) {
        $("cursor").textContent = `${mismatch}，不居中到其他楼层的实时位姿`;
        return;
      }
      const pose = freshPose();
      if (!pose) {
        $("cursor").textContent = "暂无实时机器人位姿，重定位成功且定位正常后才能居中";
        return;
      }
      centerMapOnWorld(pose.x, pose.y);
    });
    $("followRobotBtn").classList.toggle("active-tool", state.followRobot);
    $("followRobotBtn").addEventListener("click", () => {
      state.followRobot = !state.followRobot;
      $("followRobotBtn").classList.toggle("active-tool", state.followRobot);
      if (state.followRobot) {
        const mismatch = selectedMapFloorMismatchText();
        if (mismatch) {
          state.followRobot = false;
          $("followRobotBtn").classList.remove("active-tool");
          $("cursor").textContent = `${mismatch}，不能跟随其他楼层的实时位姿`;
          return;
        }
        state.view.panMode = false;
        $("panModeBtn").classList.remove("active-tool");
        const pose = freshPose();
        if (pose) centerMapOnWorld(pose.x, pose.y);
      }
    });
    $("locYaw").addEventListener("input", () => {
      const pose = state.localizeDraft;
      if (!pose) return;
      state.localizeDraft = {x: pose.x, y: pose.y, yaw: currentLocalizeYaw()};
      draw();
    });
    $("locXY").addEventListener("input", () => {
      const [xText, yText] = $("locXY").value.split(",");
      const x = Number(xText);
      const y = Number(yText);
      if (!Number.isFinite(x) || !Number.isFinite(y)) return;
      state.localizeDraft = {x, y, yaw: currentLocalizeYaw()};
      draw();
    });
    $("sendInitialPoseBtn").addEventListener("click", async () => {
      try {
        if (!state.spatialMap) throw {message: "三维空间地图尚未就绪，不能设置定位"};
        const [xText, yText] = $("locXY").value.split(",");
        const x = Number(xText);
        const y = Number(yText);
        const yaw = Number($("locYaw").value);
        if (!Number.isFinite(x) || !Number.isFinite(y)) throw {message: "定位坐标无效，请先在地图上拖箭头"};
        state.relocalizationApiLogUntil = Date.now() + 20000;
        const owner3d = state.latest && state.latest.localization_status
          && state.latest.localization_status.localization_owner === "official_mcl";
        setLog("localizeLog", owner3d
          ? "正在发布 /initialpose，等待 MCL 确认（全量关键帧预热约需 20-40 秒）..."
          : "正在发布 /initialpose，并等待开发手册 2101/1 重定位回执和定位系统更新...");
        const payload = await api("POST", "/api/localization/initialpose", {
          x,
          y,
          z: 0,
          yaw: Number.isFinite(yaw) ? yaw : 0
        });
        state.relocalizationApiLogUntil = Date.now() + 12000;
        if (payload.localization_status) {
          renderLocalizationStatus({localization_status: payload.localization_status});
        }
        setLog("localizeLog", payload);
        if (payload.confirmed) {
          state.localizeDraft = null;
          try {
            updateState(await fetchJson("/api/state"));
          } catch (err) {
            console.warn(err);
          }
          await refreshDddmrAfterLocalization();
        }
        const manualText = payload.tcp_2101_required
          ? (payload.tcp_2101_accepted ? "收到2101回执" : "未收到2101确认回执")
          : "";
        const statusText = payload.confirmed ? "重定位成功" : "重定位失败";
        $("cursor").textContent = `${statusText}${manualText ? " / " + manualText : ""} / x ${x.toFixed(3)} / y ${y.toFixed(3)} / 朝向 ${normalizeYaw(yaw).toFixed(3)} rad`;
      } catch (err) { setLog("localizeLog", err); }
    });
    $("useRobotPoseForLocBtn").addEventListener("click", () => {
      const pose = freshPose();
      if (!pose) {
        $("cursor").textContent = "暂无实时机器人位姿，不能取旧位姿做重定位初值";
        return;
      }
      setLocalizeDraft({x: pose.x, y: pose.y, yaw: pose.yaw}, "已取当前机器人位姿");
    });
    $("scanOverlayToggle").addEventListener("change", () => {
      state.scanOverlay = $("scanOverlayToggle").checked;
      draw();
    });
    $("mappingFloors").addEventListener("input", () => {
      renderMappingFloorSteps();
    });
    $("mappingMapName").addEventListener("input", () => {
      state.mappingMapNameTouched = true;
    });
    (function initMappingDraftPersistence() {
      const project = $("projectName");
      const building = $("buildingName");
      if (project && !project.value.trim()) {
        project.value = window.localStorage.getItem("m20proMappingProject") || "";
      }
      if (building && !building.value.trim()) {
        building.value = window.localStorage.getItem("m20proMappingBuilding") || "";
      }
    })();
    $("mappingMode").addEventListener("change", updateMappingModeUi);
    $("startMappingBtn").addEventListener("click", async () => {
      state.mappingCompletedStages = [];
      // While start is in flight (dense chain self-heal can take ~40s on a
      // fresh boot), saving/cancelling is meaningless and the backend gate
      // would kill the about-to-launch mapper. Disable both until start
      // returns (2026-08-31 field incident).
      const finishBtn = $("finishMappingBtn");
      const cancelBtn = $("cancelMappingBtn");
      const setInFlightButtons = (inFlight) => {
        [finishBtn, cancelBtn].forEach((btn) => {
          if (!btn) return;
          btn.disabled = inFlight;
        });
        if (inFlight && finishBtn) {
          finishBtn.dataset.prevText = finishBtn.textContent;
        }
      };
      try {
        await ensureMappingSession();
        showMappingProgress("mapping", null, false, true);
        setInFlightButtons(true);
        showMappingProgress("mapping", {
          message: "三维建图正在启动（首次可能需要自动拉起雷达数据链，约 30-60 秒），启动完成前请勿点击保存或取消"
        });
        const payload = await api("POST", "/api/mapping/start", {session_id: state.sessionId});
        state.mappingSession = payload.session || state.mappingSession;
        showMappingProgress("mapping", payload);
        // Non-blocking: a slow /api/multi_floor must never keep the
        // save/cancel buttons disabled (2026-08-31 field incident).
        loadMultiFloorWorkspace().catch(console.warn);
      }
      catch (err) {
        if (!err || !err.stage) showMappingProgress("mapping", err, true);
      }
      finally {
        setInFlightButtons(false);
      }
    });
    async function waitForMappingSaveCompletion(timeoutMs = 900000, intervalMs = 2500) {
      // 后台保存轮询: finish 已改为服务端后台 job, 断线/刷新都不影响保存本身;
      // 这里只是把结果带回界面。网络瞬时失败不中断轮询。
      const deadline = Date.now() + timeoutMs;
      while (Date.now() < deadline) {
        await new Promise(resolve => setTimeout(resolve, intervalMs));
        let status = null;
        try { status = await loadMappingRuntimeStatus(true); }
        catch (err) { status = null; }
        const job = status && status.save_job;
        if (job && job.state && job.state !== "running") {
          if (job.state === "succeeded") {
            return {
              ok: true,
              message: job.message || "三维建图结果已保存",
              archive_target: job.archive_target || "",
              session: job.session || null
            };
          }
          return {
            ok: false,
            message: job.message || "三维建图保存失败",
            code: job.code || "",
            session: job.session || null
          };
        }
      }
      return {
        ok: false,
        message: "三维建图保存超时（15 分钟仍未返回结果）；请刷新页面查看建图运行状态，后台保存可能仍在进行",
        code: "mapping_save_timeout"
      };
    }
    $("finishMappingBtn").addEventListener("click", async () => {
      showMappingProgress("saved", null, false, true);
      try {
        const payload = await api("POST", "/api/mapping/finish", {session_id: state.sessionId});
        if (payload && payload.saving) {
          state.mappingSession = payload.session || state.mappingSession;
          showMappingProgress("saved", {session: state.mappingSession, message: payload.message}, false, true);
          const finalPayload = await waitForMappingSaveCompletion();
          if (finalPayload.session) state.mappingSession = finalPayload.session;
          showMappingProgress("saved", finalPayload, finalPayload.ok === false);
          if (finalPayload.ok !== false) {
            Promise.all([loadDddmrMapAssets(true), loadMultiFloorWorkspace()]).catch(console.warn);
          }
          return;
        }
        state.mappingSession = payload.session || state.mappingSession;
        showMappingProgress("saved", payload);
        Promise.all([loadDddmrMapAssets(true), loadMultiFloorWorkspace()]).catch(console.warn);
      }
      catch (err) {
        let displayError = err;
        const starting = err && err.code === "dddmr_mapping_starting";
        if (!starting && (!err || !err.cleanup)) {
          try {
            const cleanup = await api("POST", "/api/mapping/cancel", {session_id: state.sessionId});
            state.mappingSession = cleanup.session || state.mappingSession;
            displayError = {
              ...(err || {}),
              message: `${(err && err.message) || "结束建图请求失败"}；已请求停止后台建图`,
              cleanup
            };
          } catch (cleanupError) {
            displayError = {
              ...(err || {}),
              message: `${(err && err.message) || "结束建图请求失败"}；停止后台建图也失败：${(cleanupError && cleanupError.message) || "网络不可用"}`,
              cleanup: cleanupError
            };
          }
        }
        if (starting) {
          displayError = {
            ...(err || {}),
            message: (err && err.message) || "三维建图正在启动，请稍候几秒再点保存",
            retryable: true
          };
        }
        showMappingProgress("saved", displayError, true);
      }
    });
    for (const id of ["floorRouteEntry", "floorRouteSourcePlatform", "floorRouteTargetPlatform", "floorRoutePostExit"]) {
      const control = $(id);
      if (control) control.addEventListener("change", renderFloorRouteWorkspace);
    }
    if ($("reloadFloorRoutesBtn")) $("reloadFloorRoutesBtn").addEventListener("click", () => loadFloorRoutes().catch(console.warn));
    if ($("saveFloorRouteBtn")) $("saveFloorRouteBtn").addEventListener("click", async () => {
      const routeName = $("floorRouteName");
      const entry = $("floorRouteEntry");
      const sourcePlatform = $("floorRouteSourcePlatform");
      const targetPlatform = $("floorRouteTargetPlatform");
      const postExit = $("floorRoutePostExit");
      if (!routeName || !entry || !sourcePlatform || !targetPlatform || !postExit) return;
      try {
        const payload = await api("POST", "/api/floor_routes", {
          name: routeName.value.trim(),
          entry_annotation_id: entry.value,
          source_platform_annotation_id: sourcePlatform.value,
          target_platform_annotation_id: targetPlatform.value,
          post_exit_annotation_id: postExit.value
        });
        routeName.value = "";
        await Promise.all([loadFloorRoutes(), loadMultiFloorWorkspace()]);
        showOperationFeedback("跨楼层路线已保存", payload.message || "路线已下发到导航系统");
      } catch (err) { showOperationFeedback("保存跨楼层路线失败", err, true); }
    });
    async function submitDddmrAssetRegistration() {
      const button = $("dddmrRegisterAssetBtn");
      const payload = dddmrAssetFormPayload();
      if (!payload.floor) {
        setDddmrAssetFeedback("请先填写楼层，再登记 三维资产。", "fail");
        return;
      }
      button.disabled = true;
      const oldText = button.textContent;
      button.textContent = "登记中...";
      try {
        const response = await api("POST", "/api/dddmr/map_assets", payload);
        const merged = {
          ...(state.dddmrMapAssets || {}),
          ...response,
          workspace: response.workspace || (state.dddmrMapAssets && state.dddmrMapAssets.workspace) || response.workspace || null
        };
        state.dddmrMapAssets = merged;
        if (response.floor_record) setDddmrAssetDraft(response.floor_record);
        renderDddmrMapAssets(merged);
        setDddmrAssetFeedback(response.message || `已登记 ${payload.floor} 的 三维资产`, "ok");
        await loadDddmrMapAssets(true).catch(refreshErr => {
          console.warn(refreshErr);
        });
        return response;
      } catch (err) {
        setDddmrAssetFeedback(err && err.message ? err.message : "三维资产登记失败", "fail");
        showOperationFeedback("登记 三维资产失败", err, true);
        throw err;
      } finally {
        button.disabled = false;
        button.textContent = oldText;
      }
    }
    async function submitDddmrFieldTestMode(action) {
      const endpointMap = {
        enable: "/api/dddmr/field_test_mode"
      };
      const buttonMap = {
        enable: $("dddmrEnableFieldTestModeBtn")
      };
      const labelMap = {
        enable: "确认三维模式"
      };
      const confirmMap = {
        enable: "确认三维模式会重启本机服务。确认继续？"
      };
      const button = buttonMap[action];
      const endpoint = endpointMap[action];
      if (!button || !endpoint) return;
      if (!window.confirm(confirmMap[action] || "确认三维模式？")) return;
      button.disabled = true;
      const oldText = button.textContent;
      button.textContent = "执行中...";
      try {
        const response = await api("POST", endpoint, {action});
        if (response && response.field_test_mode) {
          state.dddmrFieldTestMode = response.field_test_mode;
        } else {
          await loadState(true).catch(() => {});
        }
        renderDddmrFieldTestMode(state.dddmrFieldTestMode);
        const message = response && response.message
          ? response.message
          : `${labelMap[action]} 请求已发送`;
        setDddmrAssetFeedback(message, response && response.ok ? "ok" : "warn");
        showOperationFeedback(labelMap[action], message);
        window.setTimeout(() => {
          loadState(true).catch(() => {});
        }, 4000);
        return response;
      } catch (err) {
        setDddmrAssetFeedback(err && err.message ? err.message : `${labelMap[action]}失败`, "fail");
        showOperationFeedback(`${labelMap[action]}失败`, err, true);
        throw err;
      } finally {
        button.disabled = false;
        button.textContent = oldText;
      }
    }
    async function createDddmrFieldTestTask() {
      const button = $("dddmrCreateFieldTestTaskBtn");
      if (!button) return;
      const confirmed = window.confirm(
        "将根据当前已确认位姿在前方 1m 创建近点和单点任务。该操作不会启动任务、不会发布速度。确认创建？"
      );
      if (!confirmed) return;
      const oldText = button.textContent;
      button.disabled = true;
      button.textContent = "创建中...";
      try {
        const response = await api("POST", "/api/dddmr/field_test_task", {
          distance_m: 1.0
        });
        showOperationFeedback(
          "近点任务已创建",
          response.message || "已创建点位和单点任务；请到任务列表确认后手动启动。"
        );
        await Promise.all([
          loadDddmrFieldTestAcceptance().catch(console.warn),
          loadTasks().catch(console.warn),
          loadAnnotations().catch(console.warn)
        ]);
        return response;
      } catch (err) {
        showOperationFeedback("创建近点任务失败", err, true);
        throw err;
      } finally {
        button.disabled = false;
        button.textContent = oldText || "生成近点任务";
      }
    }
    if ($("dddmrRegisterAssetBtn")) $("dddmrRegisterAssetBtn").addEventListener("click", () => {
      submitDddmrAssetRegistration().catch(console.warn);
    });
    if ($("dddmrEnableFieldTestModeBtn")) $("dddmrEnableFieldTestModeBtn").addEventListener("click", () => {
      submitDddmrFieldTestMode("enable").catch(console.warn);
    });
    if ($("dddmrNextStepBtn")) $("dddmrNextStepBtn").addEventListener("click", () => {
      runDddmrFieldTestNextStep().catch(console.warn);
    });
    if ($("dddmrCreateFieldTestTaskBtn")) $("dddmrCreateFieldTestTaskBtn").addEventListener("click", () => {
      createDddmrFieldTestTask().catch(console.warn);
    });
    if ($("dddmrFillAssetFromMapBtn")) $("dddmrFillAssetFromMapBtn").addEventListener("click", () => {
      fillDddmrAssetDraftFromCurrentMap();
    });
    if ($("dddmrRefreshAssetsBtn")) $("dddmrRefreshAssetsBtn").addEventListener("click", () => {
      loadDddmrMapAssets(true).catch(err => {
        setDddmrAssetFeedback(err && err.message ? err.message : "三维资产清单读取失败", "fail");
        showOperationFeedback("刷新 三维资产清单失败", err, true);
      });
    });
    if ($("mapDddmrRefreshAssetsBtn")) $("mapDddmrRefreshAssetsBtn").addEventListener("click", () => {
      loadDddmrMapAssets(true).catch(err => {
        setDddmrAssetFeedback(err && err.message ? err.message : "三维资产清单读取失败", "fail");
        showOperationFeedback("刷新 三维资产清单失败", err, true);
      });
    });
    if ($("refreshDddmrFieldTestBtn")) $("refreshDddmrFieldTestBtn").addEventListener("click", () => {
      loadDddmrFieldTestAcceptance().catch(err => {
        showOperationFeedback("读取状态失败", err, true);
      });
    });
    $("markType").addEventListener("change", () => {
      syncPointDefaults(true);
    });
    $("markFloor").addEventListener("input", () => updateMarkControls());
    $("markZ").addEventListener("input", () => {
      if (!state.markDraft) return;
      const z = currentMarkZ(Number(state.markDraft.z) || 0.0);
      state.markDraft = {...state.markDraft, z};
      renderMarkPoseSummary();
      draw();
    });
    $("cancelEditMarkBtn").addEventListener("click", () => {
      setMarkEditMode(null);
      state.markDraft = null;
      state.markDraftSource = "map_click";
      renderMarkPoseSummary();
      updateMarkControls();
      $("cursor").textContent = "已取消修改";
      draw();
    });
    $("saveMarkBtn").addEventListener("click", async () => {
      try {
        const blocked = markBlockedReason();
        if (blocked) throw {message: blocked};
        const draft = state.markDraft;
        const x = Number(draft && draft.x);
        const y = Number(draft && draft.y);
        const z = currentMarkZ(Number(draft && draft.z) || 0.0);
        const yaw = normalizeYaw(draft && draft.yaw);
        if (!draft || !Number.isFinite(x) || !Number.isFinite(y)) {
          throw {message: "点位坐标无效，请先在空间视图上拖拽箭头取点"};
        }
        if (!Number.isFinite(z)) {
          throw {message: "高度 Z 无效，请填写数字，平面点可填 0"};
        }
        const editingId = state.editingAnnotationId;
        const payload = await api("POST", editingId ? "/api/annotations/update" : "/api/annotations", {
          id: editingId,
          map_id: currentAnnotationMapId(),
          source: state.markDraftSource || "map_click",
          type: $("markType").value,
          floor: $("markFloor").value.trim(),
          label: $("markLabel").value.trim(),
          building: $("markBuilding").value.trim(),
          unit: $("markUnit").value.trim(),
          house: $("markHouse").value.trim(),
          area: $("markArea").value.trim(),
          room: $("markRoom").value.trim(),
          scan_point: $("markScanPoint").value.trim(),
          result_file_prefix: $("markResultPrefix").value.trim(),
          radar: radarPlanFromSelect($("markRadarPlan").value),
          pose: {
            x,
            y,
            z,
            yaw: Number.isFinite(yaw) ? yaw : 0
          },
          manual_point_type: manualTypeByUiType[$("markType").value] || "task",
          dwell_s: asNumber("markDwell", 0),
          vendor_navigation: {
            Gait: asInteger("markGait", 12),
            Speed: asInteger("markSpeed", 1)
          }
        });
        await Promise.all([loadAnnotations(), loadFloorRoutes()]);
        state.markDraft = null;
        state.markDraftSource = "map_click";
        renderMarkPoseSummary();
        setMarkEditMode(null);
        updateMarkControls();
        draw();
        $("markLabel").value = "";
        $("markResultPrefix").value = "";
        $("markScanPoint").value = "";
        $("cursor").textContent = `已保存 ${payload.annotation.label || payload.annotation.id}`;
        showOperationFeedback(editingId ? "点位已修改" : "点位已保存", payload.message || `${payload.annotation.label || payload.annotation.id} 已保存到当前地图`);
      } catch (err) {
        $("cursor").textContent = err.message || JSON.stringify(err);
        showOperationFeedback("点位保存失败", err, true);
      }
    });
    $("useRobotPoseBtn").addEventListener("click", () => {
      const blocked = markBlockedReason();
      if (blocked) {
        $("cursor").textContent = blocked;
        updateMarkControls();
        return;
      }
      const mismatch = selectedMapFloorMismatchText();
      if (mismatch) {
        $("cursor").textContent = `${mismatch}，不能使用当前机器人位姿标到这张地图`;
        updateMarkControls();
        return;
      }
      const pose = freshPose();
      if (!pose) {
        $("cursor").textContent = "暂无实时机器人位姿，不能用旧位姿标点";
        return;
      }
      setMarkDraft(pose, "已使用当前机器人位姿", "robot_pose");
      setFloorControlValue("markFloor", displayedMapFloor());
    });
    $("createTaskBtn").addEventListener("click", async () => {
      try {
        const ids = state.taskDraftIds.slice();
        if (!ids.length) throw {message: "请先按执行顺序加入当前地图点位"};
        const route = spatialRoutePreviewForIds(ids);
        const isMultiFloor = new Set(route.floors).size >= 2;
        const endpoint = isMultiFloor ? "/api/tasks/cross_floor" : "/api/tasks";
        const payload = await api("POST", endpoint, isMultiFloor
          ? {
            name: $("taskName").value.trim() || "空间任务",
            annotation_ids: ids
          }
          : {
            name: $("taskName").value.trim(),
            map_id: currentAnnotationMapId(),
            annotation_ids: ids
          });
        $("taskName").value = "";
        state.taskDraftIds = [];
        renderTaskPoints();
        await loadTasks();
        setLog("activeTask", isMultiFloor ? "空间任务已生成；启动前确认跨楼层顺序和现场状态后再开始" : "任务已生成；启动前确认首点、顺序和现场状态后再开始");
        showOperationFeedback("任务已生成", payload.message || payload);
      } catch (err) {
        setLog("activeTask", err);
        showOperationFeedback("任务生成失败", err, true);
      }
    });
    const createCrossFloorTaskBtn = $("createCrossFloorTaskBtn");
    if (createCrossFloorTaskBtn) {
      createCrossFloorTaskBtn.addEventListener("click", async () => {
        try {
          const payload = await api("POST", "/api/tasks/cross_floor", {
            name: $("taskName").value.trim() || "跨楼层巡检任务",
            annotation_ids: state.crossFloorDraftIds.slice()
          });
          $("taskName").value = "";
          state.crossFloorDraftIds = [];
          renderCrossFloorComposer();
          await loadTasks();
          setLog("activeTask", payload);
        } catch (err) { setLog("activeTask", err); }
      });
    }
    const clearCrossFloorDraftBtn = $("clearCrossFloorDraftBtn");
    if (clearCrossFloorDraftBtn) {
      clearCrossFloorDraftBtn.addEventListener("click", () => {
        state.crossFloorDraftIds = [];
        renderCrossFloorComposer();
      });
    }
    $("annotationSearch").addEventListener("input", event => {
      state.annotationQuery = event.target.value;
      state.annotationPage = 0;
      renderAnnotations();
    });
    $("taskPointSearch").addEventListener("input", event => {
      state.taskPointQuery = event.target.value;
      renderTaskPoints();
    });
    const crossFloorPointSearch = $("crossFloorPointSearch");
    if (crossFloorPointSearch) {
      crossFloorPointSearch.addEventListener("input", event => {
        state.crossFloorPointQuery = event.target.value;
        renderCrossFloorComposer();
      });
    }
    let taskSearchTimer = null;
    $("taskSearch").addEventListener("input", event => {
      state.taskQuery = event.target.value;
      state.taskPage = 0;
      if (taskSearchTimer) clearTimeout(taskSearchTimer);
      taskSearchTimer = setTimeout(() => loadTasks().catch(console.warn), 180);
    });
    let radarResultSearchTimer = null;
    $("radarResultSearch").addEventListener("input", event => {
      state.radarResultQuery = event.target.value;
      state.radarResultPage = 0;
      if (radarResultSearchTimer) clearTimeout(radarResultSearchTimer);
      radarResultSearchTimer = setTimeout(() => loadRadarResults().catch(console.warn), 180);
    });
    $("radarResultMode").addEventListener("change", event => {
      state.radarResultMode = event.target.value;
      state.radarResultPage = 0;
      loadRadarResults().catch(console.warn);
    });
    $("refreshRadarResultsBtn").addEventListener("click", () => loadRadarResults().catch(console.warn));
    $("reloadTasksBtn").addEventListener("click", () => Promise.all([loadTasks(), loadMultiFloorWorkspace()]));
    $("frontVideoBtn").addEventListener("click", () => toggleVideo("front"));
    $("rearVideoBtn").addEventListener("click", () => toggleVideo("rear"));
    $("yoloEnabledToggle").addEventListener("change", event => setYoloEnabled(event.target.checked));
    window.addEventListener("resize", () => drawYoloOverlay(state.latest || {}));
    if ($("runPreflightBtn")) $("runPreflightBtn").addEventListener("click", runPreflight);
    if ($("refreshPreflightBtn")) $("refreshPreflightBtn").addEventListener("click", loadPreflight);
    $("startRecordingBtn").addEventListener("click", async () => {
      try {
        const duration = Number.parseInt($("recordingDuration").value, 10);
        const payload = await api("POST", "/api/recording/start", {
          duration_s: Number.isFinite(duration) ? duration : 300,
          prefix: $("recordingPrefix").value.trim()
        });
        $("recordingPrefix").value = "";
        renderRecordingStatus(payload);
        await loadRecordingList();
      } catch (err) { setLog("recordingStatus", err); }
    });
    $("stopRecordingBtn").addEventListener("click", async () => {
      try {
        setLog("recordingStatus", await api("POST", "/api/recording/stop", {}));
        setTimeout(() => Promise.all([loadRecordingStatus(), loadRecordingList()]).catch(console.warn), 800);
      } catch (err) { setLog("recordingStatus", err); }
    });
    if ($("taskRunPreflightBtn")) $("taskRunPreflightBtn").addEventListener("click", runPreflight);
    $("stopTaskBtn").addEventListener("click", async () => {
      const btn = $("stopTaskBtn");
      const oldText = btn.textContent;
      btn.disabled = true;
      btn.textContent = "停止中...";
      try {
        const payload = await api("POST", "/api/tasks/stop", {reason: "web_manual_stop"});
        renderTaskExecutionFlow(null, null);
        $("cursor").textContent = payload.message || "已发送停止指令";
        await loadTasks();
      } catch (err) {
        showOperationFeedback("停止任务失败", err, true);
      } finally {
        btn.disabled = false;
        btn.textContent = oldText;
      }
    });
    $("resetTaskSessionBtn").addEventListener("click", async () => {
      const btn = $("resetTaskSessionBtn");
      if (!window.confirm("确认清理导航会话？这会停止当前任务、发送停止/零速度指令，并清理导航会话和局部状态；不会重启服务，也不会删除点位。")) {
        return;
      }
      btn.disabled = true;
      const oldText = btn.textContent;
      btn.textContent = "清理中...";
      try {
        const payload = await api("POST", "/api/tasks/stop", {reason: "web_manual_reset"});
        renderTaskExecutionFlow(null, null);
        $("cursor").textContent = payload.message || "导航会话已清理";
        await loadTasks();
      } catch (err) {
        showOperationFeedback("清理导航会话失败", err, true);
      } finally {
        btn.disabled = false;
        btn.textContent = oldText;
      }
    });
    window.addEventListener("resize", () => {
      resizeCanvas();
      positionOpenStatusPopover();
    });
    if (window.ResizeObserver && canvas.parentElement) {
      const mapCanvasResizeObserver = new ResizeObserver(() => {
        resizeCanvas();
      });
      mapCanvasResizeObserver.observe(canvas.parentElement);
    }
    $("batteryStatusBtn").addEventListener("click", () => toggleStatusPopover("battery"));
    $("mapStatusBtn").addEventListener("click", () => toggleStatusPopover("map"));
    $("localizationStatusBtn").addEventListener("click", () => toggleStatusPopover("localization"));
    $("preflightStatusBtn").addEventListener("click", () => toggleStatusPopover("preflight"));
    $("radarStatusBtn").addEventListener("click", () => {
      toggleStatusPopover("radar");
      loadRadarStatus().catch(console.warn);
    });
    $("recordingStatusBtn").addEventListener("click", () => {
      toggleStatusPopover("recording");
      loadRecordingList().catch(err => showOperationFeedback("读取录包列表失败", err, true));
    });
    $("taskStatusBtn").addEventListener("click", () => toggleStatusPopover("task"));
    $("teleopStatusBtn").addEventListener("click", () => {
      toggleStatusPopover("teleop");
      loadTeleopStatus().catch(console.warn);
    });
    $("closeBatteryStatusBtn").addEventListener("click", () => setStatusPopover("", false));
    $("closeMapStatusBtn").addEventListener("click", () => setStatusPopover("", false));
    $("closeLocalizationStatusBtn").addEventListener("click", () => setStatusPopover("", false));
    $("closePreflightStatusBtn").addEventListener("click", () => setStatusPopover("", false));
    $("closeRadarStatusBtn").addEventListener("click", () => setStatusPopover("", false));
    $("closeRecordingStatusBtn").addEventListener("click", () => setStatusPopover("", false));
    $("refreshRecordingsBtn").addEventListener("click", () => loadRecordingList().catch(err => showOperationFeedback("读取录包列表失败", err, true)));
    $("closeTaskStatusBtn").addEventListener("click", () => setStatusPopover("", false));
    $("closeTeleopStatusBtn").addEventListener("click", () => {
      if (state.teleop.sessionId) releaseTeleop({silent: true, closePopover: true});
      else setStatusPopover("", false);
    });
    $("radarManualScanBtn").addEventListener("click", startManualRadarScan);
    $("refreshRadarStatusBtn").addEventListener("click", () => loadRadarStatus().catch(console.warn));
    $("acquireTeleopBtn").addEventListener("click", acquireTeleop);
    $("releaseTeleopBtn").addEventListener("click", () => releaseTeleop());
    $("teleopSoftStopBtn").addEventListener("click", softEmergencyStopTeleop);
    for (const button of document.querySelectorAll("[data-teleop-posture-action]")) {
      button.addEventListener("click", event => sendTeleopMotionState(event.currentTarget.dataset.teleopPostureAction));
    }
    for (const button of document.querySelectorAll("[data-teleop-gait]")) {
      button.addEventListener("click", event => sendTeleopGait(event.currentTarget.dataset.teleopGait));
    }
    $("oneKeyChargeBtn").addEventListener("click", oneKeyCharge);
    $("refreshBatteryBtn").addEventListener("click", async () => {
      try {
        updateState(await fetchJson("/api/state"));
      } catch (err) {
        showOperationFeedback("刷新电池状态失败", err, true);
      }
    });
    $("teleopZeroBtn").addEventListener("pointerdown", event => {
      if (!state.teleop.sessionId) return;
      event.preventDefault();
      zeroTeleopMotion();
    });
    for (const button of document.querySelectorAll("[data-teleop-direction]")) {
      const finishPointer = event => {
        if (!state.teleop.pointers.has(event.pointerId)) return;
        state.teleop.pointers.delete(event.pointerId);
        recomputeTeleopAxes();
        sendTeleopCommand();
      };
      button.addEventListener("pointerdown", event => {
        if (!state.teleop.sessionId) return;
        event.preventDefault();
        button.setPointerCapture(event.pointerId);
        state.teleop.pointers.set(event.pointerId, button.dataset.teleopDirection);
        recomputeTeleopAxes();
        sendTeleopCommand();
      });
      button.addEventListener("pointerup", finishPointer);
      button.addEventListener("pointercancel", finishPointer);
      button.addEventListener("lostpointercapture", finishPointer);
    }
    document.addEventListener("keydown", event => {
      const popover = $("teleopStatusPopover");
      if (!state.teleop.sessionId || !popover || popover.hidden) return;
      const target = event.target;
      if (target && target.matches && target.matches("input, textarea, select")) return;
      if (event.key === " ") {
        event.preventDefault();
        zeroTeleopMotion();
        return;
      }
      const key = event.key.length === 1 ? event.key.toLowerCase() : event.key;
      const direction = teleopKeyDirections[key];
      if (!direction) return;
      event.preventDefault();
      state.teleop.keys.set(key, direction);
      recomputeTeleopAxes();
      sendTeleopCommand();
    });
    document.addEventListener("keyup", event => {
      if (!state.teleop.sessionId) return;
      const key = event.key.length === 1 ? event.key.toLowerCase() : event.key;
      if (!state.teleop.keys.has(key)) return;
      event.preventDefault();
      state.teleop.keys.delete(key);
      recomputeTeleopAxes();
      sendTeleopCommand();
    });
    window.addEventListener("blur", () => {
      if (state.teleop.sessionId) releaseTeleop({silent: true});
    });
    document.addEventListener("visibilitychange", () => {
      if (document.hidden && state.teleop.sessionId) releaseTeleop({silent: true});
    });
    window.addEventListener("pagehide", () => {
      const sessionId = state.teleop.sessionId;
      if (!sessionId) return;
      clearLocalTeleop();
      fetch("/api/teleop/release", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({session_id: sessionId}),
        keepalive: true
      }).catch(() => {});
    });
    document.addEventListener("pointerdown", event => {
      const target = event.target;
      if (isLocalizationMapInteraction(target)) return;
      if (target && target.closest && (target.closest(".status-popover") || target.closest(".status-action"))) return;
      setStatusPopover("", false);
    });
	    $("closeOperationFeedbackBtn").addEventListener("click", () => $("operationFeedbackDialog").close());
	    $("confirmOperationFeedbackBtn").addEventListener("click", () => $("operationFeedbackDialog").close());
	    $("closeTeleopConfirmBtn").addEventListener("click", () => closeTeleopConfirm(false));
	    $("cancelTeleopConfirmBtn").addEventListener("click", () => closeTeleopConfirm(false));
	    $("confirmTeleopConfirmBtn").addEventListener("click", () => closeTeleopConfirm(true));
	    $("teleopConfirmDialog").addEventListener("cancel", event => { event.preventDefault(); closeTeleopConfirm(false); });
	    resizeCanvas();
	    setVideoActive(null);
	    if ($("workModeLocalizeBtn")) {
	      $("workModeLocalizeBtn").addEventListener("click", () => setWorkPointerMode("localize"));
	      $("workModeMarkBtn").addEventListener("click", () => setWorkPointerMode("mark"));
	      setWorkPointerMode("localize");
	    }
	    updateMapModeUi();
    renderMarkPoseSummary();
    syncPointDefaults(false);
    loadMaps()
      .then(loadAnnotations)
      .then(loadMultiFloorWorkspace)
      .then(loadFloorRoutes)
      .then(loadPreflight)
      .then(loadTasks)
      .then(() => Promise.all([loadRadarResults(), loadRecordingStatus(), loadDddmrMapAssets()]))
      .catch(console.warn);
    mainLoop();
    yoloLiveLoop();
    liveLoop();
