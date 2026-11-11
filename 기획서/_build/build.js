// 기획서 v0.3 생성기. 실행: NODE_PATH=<docx 모듈 폴더> node 기획서/_build/build.js <출력.docx>
// v0.1(계획 단계)은 git 기록과 기획서/숨비소리_AI_Agent_기획서_v0.1.docx 에 남아 있다.
// 모든 수치는 eval/results/*.json, data/cache, 노트북 01~05 출력에서 옮겼다(2026-11-11).
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, WidthType, ShadingType,
  AlignmentType, HeadingLevel, LevelFormat, ImageRun, PageBreak, BorderStyle, Footer, PageNumber,
  TableLayoutType, VerticalAlign,
} = require("docx");

const OUT = process.argv[2];
const HERE = __dirname;
const FONT = { ascii: "Malgun Gothic", eastAsia: "Malgun Gothic", hAnsi: "Malgun Gothic", cs: "Malgun Gothic" };
const NAVY = "1F3A5F", TEAL = "2A7F7F", GRAY = "5B6770", LIGHT = "EEF3F7", SAND = "F6F1E7", RED = "B5473A";
const W = 9638; // A4 본문 폭(DXA), 여백 2cm

// ---------- helpers ----------
const t = (text, o = {}) => new TextRun({ text, font: FONT, size: o.size || 19, bold: o.bold, italics: o.italics, color: o.color });
function rich(s, o = {}) { // **굵게** 지원
  return s.split(/(\*\*[^*]+\*\*)/).filter(Boolean).map(seg =>
    seg.startsWith("**") ? t(seg.slice(2, -2), { ...o, bold: true }) : t(seg, o));
}
const P = (s, o = {}) => new Paragraph({ children: rich(s, o), spacing: { after: o.after ?? 100, line: 300 }, alignment: o.align });
const H1 = (s) => new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun({ text: s, font: FONT })] });
const H2 = (s) => new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun({ text: s, font: FONT })] });
const B = (s, lvl = 0) => new Paragraph({ numbering: { reference: "bul", level: lvl }, children: rich(s), spacing: { after: 50, line: 285 } });
const BR = () => new Paragraph({ children: [new PageBreak()] });
const gap = (n = 80) => new Paragraph({ children: [], spacing: { after: n } });
const CAP = (s) => new Paragraph({ alignment: AlignmentType.CENTER, children: [t(s, { size: 16, color: GRAY })], spacing: { after: 140 } });
function img(file, widthPx) {
  const p = path.join(HERE, file);
  const buf = fs.readFileSync(p);
  const w = buf.readUInt32BE(16), h = buf.readUInt32BE(20); // PNG IHDR
  return new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 40 },
    children: [new ImageRun({ type: "png", data: buf, transformation: { width: widthPx, height: Math.round(widthPx * h / w) } })] });
}

const border = { style: BorderStyle.SINGLE, size: 4, color: "C9D3DD" };
const borders = { top: border, bottom: border, left: border, right: border };
function table(widths, header, rows, o = {}) {
  const sum = widths.reduce((a, b) => a + b, 0);
  const cell = (txt, i, isHead, shade) => new TableCell({
    width: { size: widths[i], type: WidthType.DXA }, borders,
    shading: isHead ? { type: ShadingType.CLEAR, fill: NAVY, color: "auto" } : (shade ? { type: ShadingType.CLEAR, fill: shade, color: "auto" } : undefined),
    margins: { top: 45, bottom: 45, left: 85, right: 85 }, verticalAlign: VerticalAlign.CENTER,
    children: String(txt).split("\n").map(line => new Paragraph({
      children: isHead ? [t(line, { bold: true, color: "FFFFFF", size: 17 })] : rich(line, { size: 17 }),
      spacing: { after: 0, line: 255 },
    })),
  });
  return new Table({
    width: { size: sum, type: WidthType.DXA }, columnWidths: widths, layout: TableLayoutType.FIXED,
    rows: [
      new TableRow({ tableHeader: true, children: header.map((h, i) => cell(h, i, true)) }),
      ...rows.map((r, ri) => new TableRow({ cantSplit: true, children: r.map((c, i) => cell(c, i, false, o.firstColShade && i === 0 ? LIGHT : (ri % 2 ? "FAFBFC" : undefined))) })),
    ],
  });
}
function callout(lines, fill = SAND) {
  return new Table({
    width: { size: W, type: WidthType.DXA }, columnWidths: [W], layout: TableLayoutType.FIXED,
    rows: [new TableRow({ children: [new TableCell({
      width: { size: W, type: WidthType.DXA }, shading: { type: ShadingType.CLEAR, fill, color: "auto" },
      borders: { top: { style: BorderStyle.NONE, size: 0, color: "FFFFFF" }, bottom: { style: BorderStyle.NONE, size: 0, color: "FFFFFF" }, right: { style: BorderStyle.NONE, size: 0, color: "FFFFFF" }, left: { style: BorderStyle.SINGLE, size: 24, color: TEAL } },
      margins: { top: 110, bottom: 110, left: 200, right: 160 },
      children: lines.map(l => new Paragraph({ children: rich(l, { size: 19 }), spacing: { after: 60, line: 290 } })),
    })] })],
  });
}

// ---------- content ----------
const c = [];

// 표지·요약
c.push(new Paragraph({ children: [t("제주 AI·빅데이터 활용 AI Agent 개발 챌린지 · AI Agent 기획서 v0.3", { size: 18, color: GRAY })], spacing: { after: 200 } }));
c.push(new Paragraph({ children: [t("제주 데이터 관제실", { size: 44, bold: true, color: NAVY })], spacing: { after: 80 } }));
c.push(new Paragraph({ children: [t("관광·교통 이상 신호 탐지·원인 설명 AI Agent", { size: 28, color: TEAL, bold: true })], spacing: { after: 160 } }));
c.push(new Paragraph({ border: { bottom: { style: BorderStyle.SINGLE, size: 8, color: NAVY, space: 4 } }, children: [t("팀 숨비소리  |  팀장 nnin (Data Scientist) · 팀원 hjshin93 (Data Analyst)  |  2026.11", { size: 18, color: GRAY })], spacing: { after: 220 } }));
c.push(callout([
  "**한 줄 정의** — 제주데이터허브의 유동인구·와이파이·버스 이용을 읍면동·일 단위로 살펴 **평소와 다른 날과 지역**을 찾고, 같은 날 다른 신호·제주 전체의 움직임과 기상·공휴일·축제·입도객을 대조해 **무엇이, 어디서, 얼마나, 왜(후보)** 달라졌는지 근거와 함께 알려 주는 AI Agent",
  "**누가 쓰나** — 제주빅데이터센터를 찾는 기관·사업자(관광·교통 담당 공무원, 관광사업자, 연구자). SQL·코딩 없이 화면 클릭과 한국어 질문으로 사용",
  "**무엇이 다른가** — 계산은 코드가 하고, 판단은 **센터 PC 안에서 도는 로컬 판단 모델(tev1)**이 하며, **검증기를 통과한 숫자만** 보여 줍니다. 외부 LLM으로 데이터를 보내지 않아 운영비가 0원이고, 성능은 가짜 이상·가짜 오류를 넣는 평가로 **수치로 공개**합니다.",
]));
c.push(gap(140));
c.push(table([2300, 7338], ["항목", "요약"], [
  ["활용 데이터", "제주데이터허브 Open API 8종(유동인구·와이파이·버스·정류소·AP 위치·기상·관측소·입도객) + 허브 파일 1종(축제·행사) + 공휴일 + 문서(데이터 명세서·API 문서)"],
  ["분석 기간", "2024-04-01 ~ 2025-03-31 (유동인구 12개월, 와이파이 6개월, 버스 3개월 — 수집 완료)"],
  ["Agent 구성", "질문 분류(tev1) → 조건 추출(규칙) → 도구 6종 → 원인 판정(tev1) → 문장 작성(템플릿) → 검증기"],
  ["실행 환경", "Windows · Python 3.12 · Ollama(tev1:4b, CPU 실행 가능) · 브라우저 127.0.0.1:8501, install.bat / run.bat 두 번 클릭"],
  ["현재 상태", "모든 기능 구현·실행 확인, 자동 테스트 138개 통과, 깨끗한 폴더 설치 약 2분 30초(개발 PC)"],
], { firstColShade: true }));
c.push(gap(120));
c.push(table([2300, 4038, 3300], ["평가", "결과(2026-11-11)", "읽는 법"], [
  ["이상 탐지", "가짜 이상 480건 주입, 유동인구 ±80% 변화의 **88~89%** 탐지\n평소 경보 100일당 2.8일", "±20% 같은 작은 변화는 11~23%만 탐지(한계)"],
  ["숫자 검증기", "오류 없는 브리핑 60건 **100% 통과**\n숫자 변경 94.3%·지어낸 숫자 100% 차단", "검증을 통과한 문장만 화면에 표시"],
  ["질문 분류", "처음 보는 질문 12개 중 10개(**83%**)", "키워드 규칙만 쓰면 33%"],
  ["원인 판정", "정답을 정한 10건 **10/10**\n6코어 CPU에서 원인 질문 1건 약 14초", "실제 사례로 대규모 정답 평가는 못 함, 센터 PC 실측 아님"],
], { firstColShade: true }));
c.push(BR());

// 1. 구현 목표
c.push(H1("1. 구현 목표"));
c.push(H2("1.1 문제"));
c.push(P("제주의 관광·교통 현장은 날씨, 연휴, 축제, 성수기에 따라 하루 단위로 크게 출렁입니다. 기관 담당자가 \"지난주 왜 이 지역 방문객이 늘었지?\", \"이번 달 평소와 달랐던 곳은 어디지?\"를 확인하려면 여러 데이터를 찾아 내려받고, 지역 단위를 맞추고, 비교 기준을 세워야 합니다. 데이터는 제주데이터허브에 공개돼 있지만 **어떤 데이터를 어떻게 결합할지**와 **무엇을 '평소와 다르다'로 볼지**를 정하는 데 전문 지식과 시간이 듭니다."));
c.push(H2("1.2 분석 주제"));
c.push(P("**제주 관광·교통 일 단위 신호의 이상 탐지와 원인 후보 설명.** 읍면동 유동인구, 장소별 공공와이파이 이용, 정류소별 버스 이용을 43개 읍면동 단위로 맞춰 하나의 \"관제판\"으로 묶고, 같은 요일 기준선에서 크게 벗어난 날과 지역을 찾습니다. 찾은 이상마다 같은 날 같은 지역의 다른 신호, 제주 전체(해당 읍면동 제외)의 움직임, 기상, 공휴일, 축제, 월별 입도객을 대조해 원인 후보를 근거와 함께 제시합니다."));
c.push(H2("1.3 목표와 달성 현황"));
c.push(table([2000, 3300, 4338], ["목표", "v0.1 계획(11/10)", "결과(11/11)"], [
  ["탐색 자동화", "자연어 질문으로 데이터·지역·기간 선택과 계산까지", "**달성** — 질문 분류(tev1)+조건 추출(규칙)+정해진 도구 순서. 관제판 클릭만으로도 같은 분석"],
  ["이상 탐지", "2방법 비교 후 기본값 결정, 재현율 0.8", "**부분 달성** — 큰 변화(±80%)는 0.88~0.89, 전체 평균 0.55. 2방법 차이가 작아 설명하기 쉬운 방법을 기본값으로"],
  ["원인 설명", "원인 후보를 확신도와 함께, 단정 금지", "**달성** — 7가지 원인 후보의 확률을 tev1이 산출, 문장은 \"후보\"로만 표현하고 인과 아님을 고정 문구로 표시"],
  ["신뢰성", "숫자·근거를 도구 결과와 대조, 출처 자동 표기", "**달성** — 검증기가 숫자·날짜·근거 id·원인 표현을 대조. 오류 주입 평가로 성능 공개"],
  ["실행 환경", "외부 LLM API 사용, 차단 시 오프라인 모드", "**변경** — 외부 LLM 없이 로컬 모델로 전환(보안·비용). 모델이 없으면 규칙 기반으로 자동 대체"],
], { firstColShade: true }));
c.push(BR());

// 2. 차별점
c.push(H1("2. 기존 사례와 차별점"));
c.push(P("제주 지역 데이터 대회 수상작은 **예측 정확도 경쟁**이나 **관광객·소상공인용 앱**이 중심이었습니다. 기관이 정례 모니터링에 쓰는 **탐지 → 원인 후보 → 검증** Agent는 확인하지 못했습니다."));
c.push(table([3000, 3000, 3638], ["기존 사례", "성격", "본 과제"], [
  ["DACON×제주테크노파크 대회(퇴근시간 버스 승차인원·버스 운행시간·도로 교통량·특산물 가격 예측)", "예측 모델 정확도 경쟁", "기준선(평소 값)은 계산 도구로 쓰고, 기준선을 벗어난 날의 원인 후보를 설명"],
  ["2023 제주 스마트관광 빅데이터 해커톤 「제주여행객 맞춤형 버스노선 추천 서비스」(장려상)", "관광객 대상 추천 앱", "기관 대상 모니터링·현황자료 작성 도구"],
  ["제주 공공데이터·AI 활용 창업경진대회 대상(2025 「PRICE Lab in Jeju」, 2026 「제주 로컬타임 AI」)", "소상공인·관광객 서비스", "센터 PC에 탑재해 방문 기관이 직접 실행"],
  ["일반 LLM 데이터 요약", "숫자 환각, 외부 전송·비용", "계산은 코드, 판단은 로컬 모델, 검증기 통과 숫자만 출력, 외부 전송 0"],
]));
c.push(gap(80));
c.push(table([2600, 7038], ["차별점", "구체적으로"], [
  ["여러 신호 교차 확인", "유동인구·와이파이·버스가 **같은 날 함께 움직였는지**, 섬 전체가 함께 움직였는지(해당 읍면동 제외)를 근거로 씀 → 한 지표만 볼 때보다 데이터 오류·지역 이벤트·섬 전체 흐름을 구분"],
  ["로컬 판단 모델", "Ollama 공식 라이브러리의 판단 모델 tev1(4B)이 보기별 확률을 돌려줌 → 외부 API 키·비용·데이터 반출 없이 원인 후보와 확신도 산출"],
  ["숫자 검증기", "모든 숫자에 근거 id([R1])를 달고 코드가 대조. 통과 못 한 답변은 보여 주지 않음"],
  ["성능 공개", "정답을 아는 가짜 이상·가짜 오류를 넣어 탐지율·차단율을 측정하고, 목표에 못 미친 항목도 그대로 공개"],
], { firstColShade: true }));
c.push(gap(80));
c.push(P("참고: 2026 한국관광 데이터랩 경진대회 최우수작(김포시)은 방문자 유입·승하차 데이터로 관광지 대중교통 노선을 단계적으로 구축했습니다. 관광 수요 변화를 데이터로 빠르게 읽는 일이 실제 정책 수요임을 보여 주며, 본 과제는 그 첫 단계인 \"변화 감지와 원인 파악\"을 자동화합니다.", { color: GRAY, size: 17 }));
c.push(BR());

// 3. 서비스 제안
c.push(H1("3. 서비스 제안"));
c.push(H2("3.1 데이터 활용 개요"));
c.push(P("허브의 일 단위 데이터 3종(읍면동 유동인구, AP그룹별 와이파이 이용, 정류소별 버스 이용)을 **감시 신호**로, 기상·공휴일·축제·월별 입도객을 **맥락**으로, 정류소 좌표·와이파이 AP 위치를 **위치 연결 고리**로 씁니다. 모든 신호를 43개 읍면동 단위로 맞추면 \"같은 날 같은 곳에서 여러 신호가 함께 움직였는가\"를 볼 수 있고, 이것이 원인 후보의 핵심 근거가 됩니다."));
c.push(H2("3.2 핵심 기능 (화면 4개)"));
c.push(table([2300, 7338], ["화면", "하는 일"], [
  ["① 관제판", "읍면동 × 날짜 점수 지도(빨강=평소보다 많음, 파랑=적음, 회색=수집 안 된 날)와 이상 구간 목록. 신호(유동인구·와이파이·버스), 탐지 방법, 민감도를 사이드바에서 선택"],
  ["② 상세 분석·브리핑", "이상 구간을 고르면 실제 값·기대값 그래프, 같은 날 맥락, 다른 신호·제주 전체 동반 변화, tev1 원인 판정(7개 후보 확률), 검증된 브리핑과 HTML 저장"],
  ["③ 질문하기", "\"이호동 7월 28일에 왜 사람이 많았어?\"처럼 한국어로 질문 → 분류 결과·추출 조건·검증 여부·근거(도구 호출 결과 전체)를 함께 표시"],
  ["④ 데이터 품질", "신호별 데이터 기준일, 정류소·AP의 읍면동 매핑 수와 실패 수, 버스 이용 데이터의 연결 비율"],
], { firstColShade: true }));
c.push(gap(80));
c.push(img("shots/01_board_c.png", 610));
c.push(CAP("그림 1. 관제판 — 2024-04~2025-03 유동인구 점수 지도. 세로 띠는 여러 읍면동이 함께 움직인 날(추석·설·7월 말)"));
c.push(H2("3.3 사용자 시나리오"));
c.push(B("**관광 담당 공무원(월간 점검)**: 관제판에서 지난달 이상 구간을 확인 → 상세 화면에서 원인 후보와 근거를 보고 브리핑을 HTML로 저장해 내부 보고서에 붙여 넣음"));
c.push(B("**교통 담당자(이상일 조사)**: \"성산읍 1월 버스 이용이 왜 줄었어?\"라고 질문 → 기간 내 이상 구간, 같은 날 유동인구·와이파이 변화, 기상·공휴일 맥락을 근거 id와 함께 확인"));
c.push(B("**데이터 문의**: \"버스 데이터는 어디서 가져온 거야?\" → 데이터 명세서·허브 API 문서를 검색해 출처 위치와 함께 답변"));
c.push(H2("3.4 편의성"));
c.push(B("설치는 install.bat, 실행은 run.bat 두 번 클릭. 비전공자용 단계별 설치 매뉴얼(문제 해결 표 포함) 제공"));
c.push(B("화면 클릭만으로 분석 가능, 질문하기 탭에는 예시 질문 버튼"));
c.push(B("모든 답에 데이터 기준일·출처(허브 데이터 ID)·계산 방법이 붙어 보고서에 그대로 인용 가능"));
c.push(B("원인은 \"후보 + 근거 + 확률·확신도\"로만 제시하고, 판정 모델에 넘긴 근거 문장을 화면에서 그대로 볼 수 있음"));
c.push(H2("3.5 센터 활용 방안"));
c.push(B("센터 PC에 탑재해 방문 기관이 자기 지역·기간을 지정해 셀프 분석"));
c.push(B("센터 정례 리포트(월간 \"제주 이상 신호 브리핑\") 초안 자동 생성"));
c.push(B("확장: 센터 반출 CSV(카드 이용·POS 등)를 같은 탐지·설명 구조에 연결(이번 버전에는 없음, 9장)"));
c.push(gap(160));

// 4. Agent 개발 구성
c.push(H1("4. Agent 개발 구성"));
c.push(H2("4.1 참여자의 역할"));
c.push(table([2000, 1700, 5938], ["참여자", "역할", "담당"], [
  ["nnin (팀장)", "Data Scientist", "이상 탐지 방법 설계·비교, Agent(도구·로컬 모델·검증기) 구현, 평가 설계·실행, 설치 패키지"],
  ["hjshin93", "Data Analyst", "허브 데이터 수집 결과 점검, 위치 매핑 검수, 실제 이상 사례 검토·해석, 기획서·설명자료"],
], { firstColShade: true }));
c.push(H2("4.2 Workflow"));
c.push(img("workflow_v2.png", 600));
c.push(CAP("그림 2. 질문에서 답변까지 — 판단(①④)만 로컬 모델이 하고, 계산·문장·검증은 코드가 한다"));
c.push(P("① tev1이 질문을 4종(이상 찾기·원인 설명·문서 질문·범위 밖)으로 분류하고, 모델이 '범위 밖'이라 했어도 규칙이 범위 안으로 보면 규칙을 따른다 → ② 규칙으로 읍면동(별칭·읍면 줄임말 포함)·날짜·기간·신호를 뽑고, 지역이 없으면 되묻는다 → ③ 분류별로 정해진 순서로 도구를 실행하고 결과마다 id를 붙인다 → ④ 근거를 한국어 문장으로 풀어 tev1에 넘기고 7개 원인 후보의 확률을 받는다 → ⑤ 템플릿이 결과 id를 인용한 문장만 만든다 → ⑥ 검증기가 통과시킨 답변만 보여 준다(실패 시 답변 보류와 사유 표시).", { size: 18 }));
c.push(H2("4.3 Tool / API"));
c.push(table([2200, 3700, 3738], ["도구", "입력 → 출력", "구현"], [
  ["detect_anomalies", "신호, 읍면동, 기간, 방법, 기준 → 이상일·구간(값·기대값·%·점수)", "같은 요일 앞뒤 4주 중앙값 기준선 + MAD 점수 / STL 잔차, 3일 이상 연속=지속 변화"],
  ["scan_regions", "신호, 기간 → 43개 읍면동 중 이상 구간 상위 목록", "읍면동별 탐지 후 점수순 정렬(일별 표 캐시로 6초)"],
  ["find_co_movements", "날짜, 읍면동 → 함께 움직인 다른 신호·제주 전체", "±1일 안의 점수 비교, 제주 전체는 해당 읍면동을 뺀 합계"],
  ["check_context", "날짜, 읍면동 → 기상·공휴일·축제·성수기", "가장 가까운 관측소 강수 30mm·풍속 14m/s, 공휴일 전후 1일, 지명이 명시된 축제, 월 입도객 ±5%"],
  ["search_docs", "질문 → 문서 조각과 출처", "BM25(데이터 명세서 v13, 허브 API 상세, 반출 기준, 게시판 답변)"],
  ["get_series", "신호, 읍면동, 기간 → 일 단위 시계열", "parquet 캐시 조회, 수집 안 된 날은 빈 값"],
]));
c.push(H2("4.4 사용 모델"));
c.push(table([2000, 7638], ["구분", "모델·방법"], [
  ["판단 모델", "**tev1:4b** (Ollama 공식 라이브러리, 4.3B, Q8 4.6GB, Apache 2.0) — 보기 중 하나를 고르고 보기별 확률을 돌려주는 판단 전용 모델. 질문 분류와 원인 판정 두 곳에서 사용. 작은 모델 tev1:0.8b(833MB)는 정확도가 낮아(처음 보는 질문 58%) 선택 사항으로만 안내"],
  ["규칙 대체", "Ollama나 모델이 없으면 원인 판정은 우선순위 규칙(기상 > 공휴일 > 축제 > 섬 전체 동반 > 성수기 > 판단 불가), 질문 분류는 키워드 규칙으로 자동 대체. 화면 사이드바에 연결 상태 표시"],
  ["이상 탐지", "통계 기준선(같은 요일 중앙값·MAD, STL 분해) — GPU·학습 불필요"],
  ["문서 검색", "BM25(rank-bm25). 다국어 임베딩 비교는 하지 않음"],
  ["외부 LLM", "**사용하지 않음** — 데이터가 PC 밖으로 나가지 않고 API 비용이 없다"],
  ["개발 도구", "AI 코딩 도구(Anthropic Claude Code)로 코드·테스트·문서 작성을 보조받음. 실행되는 서비스에는 포함되지 않음"],
], { firstColShade: true }));
c.push(P("**근거를 문장으로 넘기는 이유**: 같은 근거를 JSON 그대로 넘기면 tev1이 '판단 불가'로 기울었고, 한국어 문장(\"제주 전체 유동인구도 같은 날 평소보다 크게 움직였다. 즉 섬 전체에서 함께 움직였다.\")으로 풀어 쓰면 정답 원인 확률이 0.69~0.74로 올라 실제 판정 경로를 문장형으로 맞췄습니다(노트북 05).", { size: 18 }));
c.push(H2("4.5 판단 및 자율 수행 범위"));
c.push(table([2000, 7638], ["구분", "범위"], [
  ["자율 수행", "질문 분류, 지역·날짜·신호 추출, 도구 실행, 탐지·대조 계산, 원인 후보 확률 산출, 문장 작성, 검증"],
  ["사용자 확인", "지역이 없는 원인 질문은 지역을 되물음, 데이터가 없는 기간은 수집 범위를 안내, 결과 저장 여부와 화면 종료 시 삭제(ON/OFF)"],
  ["하지 않음", "원인 단정(\"후보\"와 \"인과 아님\" 문구 고정), 검증 안 된 숫자 출력, 근거 없는 원인 문장(검증기가 차단), 데이터의 외부 전송, 실시간·범위 밖 질문에 대한 추측"],
], { firstColShade: true }));
c.push(gap(160));

// 5. 데이터 활용 계획
c.push(H1("5. 데이터 활용 계획"));
c.push(H2("5.1 사용 데이터 (수집 완료, 2026-11-11)"));
c.push(table([800, 2300, 3000, 2338, 1200], ["허브 ID", "데이터명", "사용 항목", "수집 범위·규모", "용도"], [
  ["583", "읍면동 단위 내국인 유동인구", "baseDate, city, emd, visitPop", "2024-04-01~2025-03-31\n251,104행", "신호"],
  ["593", "와이파이 AP그룹별 일일 사용량", "baseDate, apGroupName, userCount", "2024-10-01~2025-03-31\n228,050행", "신호"],
  ["613", "일일 정류소별 버스 이용자 정보", "baseDate, stationId, stationName, userCount", "2025-01-01~03-31\n197,582행(승차·일반·카드)", "신호"],
  ["612", "버스 정류소 기본 정보", "stationId, stationName, 주소, 위경도", "4,352개", "위치"],
  ["618", "제주 공공와이파이 AP 정보", "apGroupName, addressDong, 위경도, category", "2,615개(8회 반복 수집)", "위치"],
  ["579·578", "일별 기상 정보 / 기상관측소", "관측소, 일강수량, 최대풍속 / 좌표", "2024-04-01~2025-03-30\n12,176행 / 42곳", "맥락"],
  ["580", "방문목적별 입도객 현황", "dtYearMonth, visitPurpose, visitorCnt", "2024-04~2025-07, 144행", "맥락"],
  ["761", "VISIT JEJU 축제행사콘텐츠(파일)", "콘텐츠명, 시작일, 종료일", "분석 기간 161건 중 9건 연결", "맥락"],
  ["-", "대한민국 공휴일", "holidays 오픈소스 패키지", "전날·당일·다음날", "맥락"],
  ["-", "데이터 명세서 v13, 허브 API 상세, 반출 기준", "문서 본문", "각 문서 첫 줄에 출처 URL·확인일", "문서 검색"],
]));
c.push(P("수집했지만 이번 버전에서 쓰지 않는 데이터: 국가별 입도객(582), 버스 노선(611), 버스 일일 승객수(617), 와이파이 일일 사용자수(586).", { size: 17, color: GRAY }));
c.push(H2("5.2 수집"));
c.push(B("허브 Open API(프로젝트 키, 페이지당 100행). 데이터별 일일 호출 한도 1,000회 — 대용량 3종(583·593·613)은 증설을 신청해 **5,000회 승인**받음(2026-11-11)"));
c.push(B("한도에 걸리면 받던 페이지를 저장하고 다음 날 이어받음. **끝까지 받은 요청(월·일) 단위만** 분석에 사용 — 받다 만 달은 날짜가 무작위로 빠져 있기 때문"));
c.push(B("AP 정보(618)는 페이지 순서가 호출마다 바뀌어 같은 요청을 8회 반복해 합집합(2,615개로 수렴)"));
c.push(B("분석 기간을 2024-04~2025-03으로 정한 이유: 허브 일별 기상(579)이 2025년 3월 말에서 끝남"));
c.push(H2("5.3 전처리와 결합"));
c.push(table([2000, 7638], ["대상", "방법"], [
  ["유동인구", "성별·연령대 행을 날짜·읍면동별로 합산(일 방문인구), city+emd를 43개 읍면동 이름으로 정규화"],
  ["정류소·AP → 읍면동", "주소에서 읍면동 추출 → 실패하면 주소로 확정된 다른 정류소 중 2km 이내 가장 가까운 곳 → 그래도 실패하면 '매칭 실패'로 따로 집계(정류소 4,352개 중 66개 실패, AP그룹 1,475개 매핑·6개 실패)"],
  ["버스 이용(613)", "613의 정류소ID(7자리)는 612(9자리)와 체계가 달라 겹치지 않음을 확인 → 기호를 뺀 정류소 이름이 한 읍면동에만 있을 때만 연결. 이용자 수 기준 **87.9% 연결**, 같은 이름이 여러 읍면동에 있어 제외 6.5%, 매칭 실패 5.6%"],
  ["기상", "읍면동 중심(정류소 좌표 평균, 정류소가 없으면 AP 좌표)에서 가장 가까운 관측소 → 43개 읍면동 모두 연결"],
  ["축제(761)", "원본에 장소가 없음 → 행사명에 지명이 **명시된** 7일 이하 행사만 연결('월대천'의 '대천'처럼 단어 중간 지명은 불인정, '취소' 행사 제외)"],
  ["공통", "수집되지 않은 날은 0이 아니라 빈 값 — 공백을 '급감'으로 잘못 읽지 않기 위해"],
], { firstColShade: true }));
c.push(H2("5.4 이용조건과 보안"));
c.push(B("허브 데이터는 제주데이터허브 이용약관에 따라 출처를 표기해 사용(데이터 상세 페이지에 별도 라이선스 표기 없음, 2026-11-10 확인)"));
c.push(B("게시판 답변에 따라 허브 공개 원본·전처리본(parquet 9MB)은 출처·전처리 명세와 함께 결과물에 포함. **허브 데이터목록 xlsx는 결과물·저장소에서 제외**"));
c.push(B("허브 API 키는 .env에만 두고 결과물에는 발급·설정 방법만(.env.example)"));
c.push(B("개인 단위 데이터 없음(모두 집계값). 판단은 PC 안의 로컬 모델이 하므로 데이터가 외부로 나가지 않음"));
c.push(B("화면은 127.0.0.1에서만 열림. 저장한 브리핑은 data/results에 두고 기본 설정으로 화면 종료 시 삭제"));
c.push(gap(160));

// 6. 검증·평가
c.push(H1("6. 검증과 평가"));
c.push(P("실제 이상에는 정답이 없으므로, **정답을 아는 가짜 이상·가짜 오류를 넣어** 측정했습니다. 모든 평가는 `python -m eval.<이름>`으로 다시 돌릴 수 있고 결과는 eval/results에 저장됩니다.", { size: 18 }));
c.push(H2("6.1 이상 탐지 — 가짜 이상 주입(inject_eval)"));
c.push(P("실제 시계열의 '평범한 날'(점수 2 미만)에 하루 급변(1일) 또는 지속 변화(4일 연속)를 ±20·40·80% 크기로 넣고, 신호마다 480회 반복했습니다. 기본 설정(같은 요일 중앙값, 점수 3.5)의 결과입니다.", { size: 18 }));
c.push(table([2000, 1900, 1900, 1900, 1938], ["신호(읍면동 수)", "±80%", "±40%", "±20%", "평소 경보\n(100일당)"], [
  ["유동인구(43)", "88~89%", "59%", "11~23%", "2.8일"],
  ["와이파이(43)", "43~65%", "3~20%", "0~3%", "3.2일"],
  ["버스(41, 3개월)", "75~85%", "13~16%", "0~2%", "3.6일"],
]));
c.push(P("**기본 방법 결정**: 같은 경보 빈도로 맞추면 STL 잔차가 유동인구 +2.1%p, 와이파이 +5.5%p, 버스 −0.9%p로 차이가 작아, 담당자에게 설명하기 쉬운 '같은 요일 중앙값'을 기본으로 두고 STL은 화면에서 고를 수 있게 했습니다. 와이파이는 날마다 변동이 커서 큰 변화 위주로만 읽어야 합니다.", { size: 18 }));
c.push(H2("6.2 숫자 검증기 — 가짜 오류 주입(verify_eval)"));
c.push(table([3600, 2400, 3638], ["넣은 오류(실제 브리핑 60건)", "차단율", "비고"], [
  ["오류 없음(원문)", "통과 100%", "정상 문장을 잘못 막지 않음"],
  ["숫자 하나를 5~30% 변경", "94.3% (53건)", "반올림 범위 안의 작은 변경은 통과할 수 있음"],
  ["근거 표시 [Rn] 삭제", "100% (60건)", ""],
  ["다른 결과로 근거 바꿔치기", "92.3% (13건)", "같은 날짜가 든 결과로 바꾸면 통과(1건)"],
  ["결과에 없는 숫자 문장 추가", "100% (60건)", ""],
  ["근거 없는 원인 단정 추가", "100% (60건)", "원인 문장은 맥락·동반 변화 근거 필수"],
]));
c.push(H2("6.3 로컬 모델 — 질문 분류와 원인 판정"));
c.push(table([2600, 3600, 3438], ["평가", "결과", "조건"], [
  ["질문 분류(intent_probe)", "처음 보는 질문 12개: tev1:4b 83%, 0.8b 58%, 키워드 규칙 33%\n설계에 쓴 질문 24개: 모델+규칙 결합 96%", "처음 보는 질문은 결합 방식 설계 전에 적어 두고 평가에만 사용"],
  ["원인 판정(tev1_probe)", "정답을 정한 10건: 4B 10/10, 0.8B 5~6/10", "기상·연휴·축제·관광 수요·데이터 오류·판단 불가, 손수 만든 사례"],
  ["문서 검색(rag_probe)", "답이 있는 문서가 상위 3개 안: 설계 질문 7/10 → 9/10, 따로 둔 질문 6/6", "제목 가중·우리 문서 추가·문서당 조각 하나로 개선"],
  ["처리 시간(speed_probe)", "질문 → 검증된 답변, 중앙값. **6코어 CPU: 원인 질문 13.7초, 지역 훑기 4.8초, 문서·범위 밖 4~5초**\nGPU 0.6초 이하, 모델 서버 없음(규칙 기반) 2.5초 이하", "개발 PC(i7-13700K)를 센터 PC와 같은 6코어로 묶어 측정. 센터 PC는 코어당 성능이 낮아 더 느릴 수 있음(미확인)"],
]));
c.push(H2("6.4 실제 데이터에서 확인한 사례"));
c.push(table([2600, 3900, 3138], ["사례", "데이터가 보여 준 것", "Agent 판정"], [
  ["추석 2024-09-16~17, 설 2025-01-28~30", "이상 읍면동이 가장 많은 날(최대 35곳). 성산읍 09-16 +148.7%, 제주 전체도 증가", "공휴일·연휴 73.4% (성산읍)"],
  ["이호동 2024-07-26~29", "+103.8%(07-28), 같은 날 제주 전체 유동인구도 증가", "관광 수요 변화 66.5%"],
  ["이호동 2024-08-02", "+48.0%, 이호테우축제 첫날", "축제·행사 75.9%"],
  ["삼도1동 2025-03-28~30", "+170.1%, 와이파이(점수 13.7)·버스도 함께 증가 → 데이터 오류 가능성 낮음", "관광 수요 변화 62.5%, 단 맞는 행사를 데이터에서 찾지 못해 **실제 원인은 미확인**"],
]));
c.push(img("shots/03_briefing_c.png", 560));
c.push(CAP("그림 3. 상세 화면의 검증된 브리핑(삼도1동) — 반대 방향의 비수기 표시는 원인 후보에서 빼고 참고로만 표시"));
c.push(H2("6.5 1년치 데이터 점검에서 찾아 고친 문제"));
c.push(B("**섬 전체 비교에 해당 지역이 섞임**: 한 곳의 큰 급증이 제주 전체 합계까지 끌어올려 '섬 전체 흐름'으로 읽힐 수 있었음 → 해당 읍면동을 뺀 합계로 비교"));
c.push(B("**반대 방향 맥락**: 급증한 날 '비수기'를 원인 후보로 적던 문장 → 방향이 맞지 않으면 참고로만 표시"));
c.push(B("**검증기 허점**: 지명 속 숫자('용담1동'의 1)를 근거 숫자로 인정 → 글자에 붙은 숫자는 제외(근거 바꿔치기 차단 76.9% → 92.3%)"));
c.push(B("**지역 훑기 속도**: 기준선을 날짜마다 따로 계산 → 한 번에 계산(실제 시계열 127개 결과 동일, 6코어 CPU에서 9.2초 → 4.8초)"));
c.push(P("각 수정마다 문제를 재현하는 자동 테스트를 먼저 만들고 고쳤습니다(전체 147개).", { size: 18 }));
c.push(gap(160));

// 7. 개발·탑재 계획
c.push(H1("7. 개발·탑재 계획"));
c.push(H2("7.1 구현 범위"));
c.push(table([1500, 8138], ["구분", "범위"], [
  ["구현 완료", "허브 수집기(한도·이어받기), 위치 매핑, 이상 탐지 2방법·구간 묶기, 원인 맥락 대조, 동반 변화, 문서 검색(BM25), 로컬 판단 모델 연동과 규칙 대체, 로컬 Agent(질문하기), 검증기, HTML 브리핑·저장/삭제, 화면 4개, 평가 3종, install.bat/run.bat, 매뉴얼·데이터 명세, 노트북 5개"],
  ["이번 버전 제외", "센터 반출 CSV 업로드, 외국인 유동인구(589), 2025년 4월 이후 기간(허브 기상 미제공), 이상 발생 알림"],
], { firstColShade: true }));
c.push(H2("7.2 기술 환경"));
c.push(table([2300, 7338], ["항목", "내용"], [
  ["언어·런타임", "Python 3.12 (Windows 11에서 설치·실행 검증)"],
  ["라이브러리(버전 고정)", "pandas 3.1.1, numpy 2.5.4, pyarrow 26.0.1, statsmodels 0.15.0, holidays 0.108, rank-bm25 0.2.2, plotly 7.1.0, streamlit 1.67.0, requests 2.34.2, python-dotenv 1.2.4, openpyxl 3.1.5"],
  ["판단 모델", "Ollama + tev1:4b (127.0.0.1:11434, 설치 시 자동 내려받기)"],
  ["데이터 저장", "parquet 캐시(9MB, 결과물 포함), 상태·로그는 data/state"],
  ["품질 관리", "pytest 자동 테스트 147개, 화면 스모크 테스트(Streamlit AppTest), 깨끗한 폴더 설치 재현"],
], { firstColShade: true }));
c.push(H2("7.3 UI 구성"));
c.push(img("shots/04_ask_c.png", 500));
c.push(CAP("그림 4. 질문하기 — 분류 결과(tev1 87%), 추출한 읍면동·날짜, 검증 통과 표시, 근거 id가 붙은 답변"));
c.push(B("Streamlit 웹 화면, 1920×1080·Chrome/Edge 기준. 사이드바(신호·탐지 방법·민감도·저장 삭제·판단 모델 연결 상태) + 탭 4개(3.2절)"));
c.push(H2("7.4 센터 실행환경과 외부 서비스 의존성"));
c.push(table([3000, 6638], ["항목", "대응"], [
  ["센터 PC(i7-8700, GTX 1060 3GB, RAM 32GB)", "tev1:4b(4.6GB)는 VRAM 3GB에 다 올라가지 않아 CPU로 실행 — 6코어로 묶은 CPU에서 원인 질문 약 14초(6.3절). 탐지·검색은 GPU 불필요. **센터 PC 실측은 미확인**"],
  ["디스크", "Python 가상환경 약 0.9GB + 모델 4.6GB + 데이터 9MB"],
  ["설치", "① Python 3.12 설치 ② Ollama 설치 ③ install.bat(패키지·모델 자동) ④ run.bat — 단계별 매뉴얼과 문제 해결 표 제공"],
  ["실행 방식", "로컬 서버(127.0.0.1:8501) + 브라우저, 판단 모델도 로컬(127.0.0.1:11434)"],
  ["외부 접속 주소", "설치할 때만: python.org(Python), pypi.org·files.pythonhosted.org(패키지), ollama.com(Ollama·모델)\n데이터 갱신할 때만: open.jejudatahub.net(허브 Open API)\n**분석·질문 중에는 외부 접속 없음**"],
  ["보안 정책(DLP)", "분석 데이터가 외부로 나가는 통신이 없음. Ollama가 없거나 막히면 규칙 기반 판정으로 자동 전환"],
  ["결과 보존", "저장한 브리핑은 data/results, 사이드바 'ON'이면 화면 종료 시 삭제(기본 ON), 수동 삭제 버튼"],
  ["운영 비용", "외부 API 사용 없음 → 질문당 비용 0원"],
], { firstColShade: true }));
c.push(H2("7.5 남은 일정"));
c.push(table([1500, 8138], ["날짜", "작업"], [
  ["11/12~17", "설명자료(결과 설명서) 작성, 화면 문구 다듬기 (6코어 CPU 속도 측정은 11/11 완료)"],
  ["11/18", "결과물 ZIP 구성(코드·매뉴얼·데이터 명세·평가 결과·캐시, 키·허브 목록 파일 제외 확인), 깨끗한 폴더 설치 재현"],
  ["11/19", "기획서 PDF 확정, 제출 전 최종 점검 → 11/20 10:00 마감 전 팀장 제출"],
]));
c.push(gap(160));

// 8. 한계
c.push(H1("8. 한계와 대응"));
c.push(table([3300, 6338], ["한계", "대응"], [
  ["동반 변화·맥락은 상관관계이며 인과가 아님", "\"원인 후보 + 근거 + 확률\"로만 표현, 모든 답변 끝에 \"인과를 뜻하지 않습니다\" 고정"],
  ["작은 변화(±20%)는 대부분 놓침, 와이파이는 큰 변화도 절반가량", "평가 결과를 화면·문서에 공개, 민감도와 방법을 사용자가 조절"],
  ["원인 판정의 대규모 정답 평가가 없음(손수 만든 10건 + 실제 사례 확인)", "판정 모델에 넘긴 근거 문장을 화면에 그대로 보여 주어 사람이 확인 가능"],
  ["분석 기간이 1년(버스 3개월, 와이파이 6개월) — 작년 같은 달 비교 불가, 시리즈 끝은 앞쪽 데이터로만 기준선", "데이터 기준일을 모든 화면에 표시, 기간 밖 질문은 수집 범위를 안내"],
  ["축제 데이터에 장소가 없어 9건만 연결", "지명이 명시된 경우만 연결하고 추측하지 않음, 못 찾으면 '미확인'"],
  ["버스는 승차·일반·카드만, 이용자 12.1%는 읍면동 연결 불가", "데이터 품질 탭과 명세서에 비율 공개"],
  ["검증기는 숫자·날짜·근거 id를 확인하지만 문장 뜻까지는 보장하지 않음", "근거 표(도구 결과 전체)를 답변 아래 펼쳐 볼 수 있게 함"],
  ["센터 PC(i7-8700) 실측 속도 미확인(6코어로 묶어 잰 원인 질문 약 14초)", "기다리는 동안 진행 표시, 느리면 규칙 판정으로 전환 안내(Ollama를 끄면 자동 전환, 질문 1건 2.5초 이하)"],
], { firstColShade: true }));
c.push(gap(140));

// 9. 기대 효과
c.push(H1("9. 기대 효과와 확장"));
c.push(B("**기관**: 현황자료 작성 전 \"무엇이, 어디서 달라졌는지\" 확인 시간을 줄이고, 근거·출처가 붙은 수치를 보고서에 바로 인용"));
c.push(B("**센터**: 외부 API 비용·데이터 반출 걱정 없는 방문자 셀프 분석 도구, 월간 이상 신호 브리핑 정례화"));
c.push(B("**확장**: 센터 반출 CSV(카드·POS) 연결과 반출 기준(10 미만 값·역산) 검사, 최근 기간 기상 보강, 이상 발생 알림"));
c.push(gap(140));
c.push(H2("부록. 출처"));
c.push(P("제주데이터허브(jejudatahub.net) 데이터 상세 페이지·API 기술문서·반출 기준 공지(48), 대회 게시판 공식 답변(2026-10~11), Ollama 라이브러리 tev1 페이지, DACON 제주 대회 페이지, 시사매일(2026.08.06), 코리아타임뉴스(2025.08.06), 일간투데이(김포시 사례). 2023 해커톤 수상작은 검색 요약 기준이며 기사 원문은 확인하지 못함. 평가 수치는 결과물의 eval/results/*.json과 노트북 01~05에서 재현 가능.", { size: 17, color: GRAY }));

// ---------- document ----------
const doc = new Document({
  creator: "숨비소리",
  title: "제주 데이터 관제실 AI Agent 기획서 v0.3",
  styles: {
    default: { document: { run: { font: FONT, size: 19 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { font: FONT, size: 30, bold: true, color: NAVY }, paragraph: { spacing: { before: 120, after: 160 }, keepNext: true, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { font: FONT, size: 22, bold: true, color: TEAL }, paragraph: { spacing: { before: 200, after: 80 }, keepNext: true, outlineLevel: 1 } },
    ],
  },
  numbering: { config: [
    { reference: "bul", levels: [
      { level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 360, hanging: 240 } } } },
      { level: 1, format: LevelFormat.BULLET, text: "–", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 240 } } } } ] },
  ] },
  sections: [{
    properties: { page: { size: { width: 11906, height: 16838 }, margin: { top: 1134, bottom: 1134, left: 1134, right: 1134 } } },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [
      new TextRun({ text: "숨비소리 · 제주 데이터 관제실 기획서 v0.3  |  ", font: FONT, size: 16, color: GRAY }),
      new TextRun({ children: [PageNumber.CURRENT], font: FONT, size: 16, color: GRAY }) ] })] }) },
    children: c,
  }],
});
Packer.toBuffer(doc).then(buf => { fs.writeFileSync(OUT, buf); console.log("written", OUT); });
