"use strict";

// 외부(AWS·서버) 문자열은 모두 textContent로만 넣는다. innerHTML은 사용하지 않는다.

const $ = (id) => document.getElementById(id);

function el(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined && text !== null) node.textContent = String(text);
  if (className) node.className = className;
  return node;
}

class ApiError extends Error {
  constructor(code, message) {
    super(message);
    this.code = code;
  }
}

async function getJson(path) {
  let response;
  try {
    response = await fetch(path, { headers: { Accept: "application/json" } });
  } catch {
    throw new ApiError("NETWORK_ERROR", "서버에 연결하지 못했습니다. 서버 실행 상태를 확인하세요.");
  }

  let body = null;
  try {
    body = await response.json();
  } catch {
    // 본문이 JSON이 아닌 경우
  }

  if (!response.ok) {
    const detail = body && typeof body.detail === "object" ? body.detail : null;
    throw new ApiError(
      (detail && detail.code) || `HTTP_${response.status}`,
      (detail && detail.message) || `요청이 실패했습니다. (HTTP ${response.status})`
    );
  }
  if (!body) throw new ApiError("INVALID_RESPONSE", "서버 응답을 해석하지 못했습니다.");
  return body;
}

// ---- 상태 표시 (로딩 / 빈 목록 / 오류) ----

function showStatus(id, kind, message, code) {
  const box = $(id);
  box.className = `status ${kind}`;
  box.replaceChildren();
  if (!kind) return;
  if (code) box.append(el("strong", code), " ");
  box.append(message);
}

function setCount(id, state, value) {
  const dd = $(id);
  dd.className = state;
  if (state === "loading") dd.textContent = "조회 중…";
  else if (state === "error") dd.textContent = "조회 실패";
  else dd.textContent = `${value}개`;
}

// ---- 각 리소스 렌더링 ----

async function loadContext() {
  showStatus("context-status", "loading", "계정 정보를 조회하는 중입니다…");
  for (const id of ["ctx-account", "ctx-region", "ctx-arn"]) $(id).textContent = "조회 중…";
  try {
    const data = await getJson("/api/context");
    $("ctx-account").textContent = data.account_id;
    $("ctx-region").textContent = data.region;
    $("ctx-arn").textContent = data.caller_arn;
    showStatus("context-status", "", "");
  } catch (err) {
    for (const id of ["ctx-account", "ctx-region", "ctx-arn"]) $(id).textContent = "조회 실패";
    showStatus("context-status", "error", err.message, err.code);
  }
}

async function loadEc2() {
  const table = $("ec2-table");
  const tbody = table.querySelector("tbody");
  table.hidden = true;
  showStatus("ec2-status", "loading", "EC2 인스턴스를 조회하는 중입니다…");
  setCount("count-ec2", "loading");
  try {
    const data = await getJson("/api/ec2");
    tbody.replaceChildren(
      ...data.items.map((item) => {
        const tr = el("tr");
        const state = el("td");
        state.append(el("span", item.state, `badge state-${item.state}`));
        tr.append(
          el("td", item.name),
          el("td", item.instance_id, "mono"),
          state,
          el("td", item.instance_type),
          el("td", item.private_ip ?? "-", "mono"),
          el("td", item.public_ip ?? "-", "mono")
        );
        return tr;
      })
    );
    setCount("count-ec2", "ok", data.count);
    if (data.count === 0) {
      showStatus("ec2-status", "empty", "이 리전에 EC2 인스턴스가 없습니다.");
    } else {
      showStatus("ec2-status", "", "");
      table.hidden = false;
    }
  } catch (err) {
    tbody.replaceChildren();
    setCount("count-ec2", "error");
    showStatus("ec2-status", "error", err.message, err.code);
  }
}

async function loadS3() {
  const list = $("s3-list");
  list.hidden = true;
  showStatus("s3-status", "loading", "S3 버킷을 조회하는 중입니다…");
  setCount("count-s3", "loading");
  try {
    const data = await getJson("/api/s3");
    list.replaceChildren(...data.items.map((b) => el("li", b.name, "mono")));
    setCount("count-s3", "ok", data.count);
    if (data.count === 0) {
      showStatus("s3-status", "empty", "계정에 S3 버킷이 없습니다.");
    } else {
      showStatus("s3-status", "", "");
      list.hidden = false;
    }
  } catch (err) {
    list.replaceChildren();
    setCount("count-s3", "error");
    showStatus("s3-status", "error", err.message, err.code);
  }
}

function describeProtocol(p) {
  if (p.IpProtocol === "-1") return "전체";
  return String(p.IpProtocol).toUpperCase();
}

function describePorts(p) {
  if (p.IpProtocol === "-1" || p.FromPort === undefined) return "전체";
  if (p.FromPort === p.ToPort) return String(p.FromPort);
  return `${p.FromPort}-${p.ToPort}`;
}

function describeSources(p) {
  const sources = [];
  for (const r of p.IpRanges || []) sources.push(r.CidrIp);
  for (const r of p.Ipv6Ranges || []) sources.push(r.CidrIpv6);
  for (const g of p.UserIdGroupPairs || []) sources.push(g.GroupId);
  for (const pl of p.PrefixListIds || []) sources.push(pl.PrefixListId);
  return sources;
}

function renderSecurityGroup(sg) {
  const card = el("article", null, "sg-card");
  const head = el("header");
  head.append(el("h3", sg.GroupName), el("span", sg.GroupId, "mono muted"));
  card.append(head);

  const perms = sg.IpPermissions || [];
  if (perms.length === 0) {
    card.append(el("p", "인바운드 규칙이 없습니다.", "muted"));
    return card;
  }

  const table = el("table");
  const thead = el("thead");
  const hr = el("tr");
  hr.append(el("th", "프로토콜"), el("th", "포트"), el("th", "소스"));
  thead.append(hr);
  const tbody = el("tbody");
  for (const p of perms) {
    const tr = el("tr");
    const src = el("td", null, "mono");
    const sources = describeSources(p);
    if (sources.length === 0) src.textContent = "-";
    sources.forEach((s, i) => {
      if (i > 0) src.append(el("br"));
      src.append(s);
    });
    tr.append(el("td", describeProtocol(p)), el("td", describePorts(p), "mono"), src);
    tbody.append(tr);
  }
  table.append(thead, tbody);
  const wrap = el("div", null, "table-wrap");
  wrap.append(table);
  card.append(wrap);
  return card;
}

async function loadSecurityGroups() {
  const list = $("sg-list");
  list.replaceChildren();
  showStatus("sg-status", "loading", "보안 그룹을 조회하는 중입니다…");
  setCount("count-sg", "loading");
  try {
    const data = await getJson("/api/security-groups");
    list.replaceChildren(...data.items.map(renderSecurityGroup));
    setCount("count-sg", "ok", data.count);
    if (data.count === 0) showStatus("sg-status", "empty", "이 리전에 보안 그룹이 없습니다.");
    else showStatus("sg-status", "", "");
  } catch (err) {
    setCount("count-sg", "error");
    showStatus("sg-status", "error", err.message, err.code);
  }
}

// ---- 조회 / 탭 ----

async function refreshAll() {
  const btn = $("refresh-btn");
  btn.disabled = true;
  btn.textContent = "조회 중…";
  try {
    await Promise.all([loadContext(), loadEc2(), loadS3(), loadSecurityGroups()]);
    $("last-fetched").textContent = new Date().toLocaleString("ko-KR");
  } finally {
    btn.disabled = false;
    btn.textContent = "조회";
  }
}

function selectTab(name) {
  for (const tab of document.querySelectorAll("[data-tab]")) {
    tab.setAttribute("aria-selected", String(tab.dataset.tab === name));
  }
  for (const panel of document.querySelectorAll(".panel")) {
    panel.hidden = panel.id !== `tab-${name}`;
  }
}

for (const tab of document.querySelectorAll("[data-tab]")) {
  tab.addEventListener("click", () => selectTab(tab.dataset.tab));
}
$("refresh-btn").addEventListener("click", refreshAll);

refreshAll();
