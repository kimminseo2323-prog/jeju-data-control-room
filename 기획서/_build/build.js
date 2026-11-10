const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, WidthType, ShadingType,
  AlignmentType, HeadingLevel, LevelFormat, ImageRun, PageBreak, BorderStyle, Footer, PageNumber,
  TableLayoutType, VerticalAlign,
} = require("docx");

const OUT = process.argv[2];
const IMG = path.join(__dirname, "workflow.png");
const FONT = { ascii: "Malgun Gothic", eastAsia: "Malgun Gothic", hAnsi: "Malgun Gothic", cs: "Malgun Gothic" };
const NAVY = "1F3A5F", TEAL = "2A7F7F", GRAY = "5B6770", LIGHT = "EEF3F7", SAND = "F6F1E7", RED = "B5473A";
const W = 9638; // A4 content width (DXA) with 2cm margins

// ---------- helpers ----------
const t = (text, o = {}) => new TextRun({ text, font: FONT, size: o.size || 19, bold: o.bold, italics: o.italics, color: o.color });
function rich(s, o = {}) { // **bold** support
  return s.split(/(\*\*[^*]+\*\*)/).filter(Boolean).map(seg =>
    seg.startsWith("**") ? t(seg.slice(2, -2), { ...o, bold: true }) : t(seg, o));
}
const P = (s, o = {}) => new Paragraph({ children: rich(s, o), spacing: { after: o.after ?? 100, line: 300 }, alignment: o.align });
const TODO = (s) => new Paragraph({ children: [t("[구현 후 기입] " + s, { italics: true, color: RED })], spacing: { after: 100 } });
const H1 = (s) => new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun({ text: s, font: FONT })] });
const H2 = (s) => new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun({ text: s, font: FONT })] });
const B = (s, lvl = 0) => new Paragraph({ numbering: { reference: "bul", level: lvl }, children: rich(s), spacing: { after: 60, line: 290 } });
const N = (s) => new Paragraph({ numbering: { reference: "num", level: 0 }, children: rich(s), spacing: { after: 60, line: 290 } });
const BR = () => new Paragraph({ children: [new PageBreak()] });

const border = { style: BorderStyle.SINGLE, size: 4, color: "C9D3DD" };
const borders = { top: border, bottom: border, left: border, right: border };
function table(widths, header, rows, o = {}) {
  const sum = widths.reduce((a, b) => a + b, 0);
  const cell = (txt, i, isHead, shade) => new TableCell({
    width: { size: widths[i], type: WidthType.DXA }, borders,
    shading: isHead ? { type: ShadingType.CLEAR, fill: NAVY, color: "auto" } : (shade ? { type: ShadingType.CLEAR, fill: shade, color: "auto" } : undefined),
    margins: { top: 50, bottom: 50, left: 90, right: 90 }, verticalAlign: VerticalAlign.CENTER,
    children: String(txt).split("\n").map(line => new Paragraph({
      children: isHead ? [t(line, { bold: true, color: "FFFFFF", size: 17 })] : rich(line, { size: 17 }),
      spacing: { after: 0, line: 260 },
    })),
  });
  return new Table({
    width: { size: sum, type: WidthType.DXA }, columnWidths: widths, layout: TableLayoutType.FIXED,
    rows: [
      new TableRow({ tableHeader: true, children: header.map((h, i) => cell(h, i, true)) }),
      ...rows.map((r, ri) => new TableRow({ children: r.map((c, i) => cell(c, i, false, o.firstColShade && i === 0 ? LIGHT : (ri % 2 ? "FAFBFC" : undefined))) })),
    ],
  });
}
const gap = (n = 80) => new Paragraph({ children: [], spacing: { after: n } });
function callout(lines, fill = SAND) {
  return new Table({
    width: { size: W, type: WidthType.DXA }, columnWidths: [W], layout: TableLayoutType.FIXED,
    rows: [new TableRow({ children: [new TableCell({
      width: { size: W, type: WidthType.DXA }, shading: { type: ShadingType.CLEAR, fill, color: "auto" },
      borders: { top: { style: BorderStyle.NONE, size: 0, color: "FFFFFF" }, bottom: { style: BorderStyle.NONE, size: 0, color: "FFFFFF" }, right: { style: BorderStyle.NONE, size: 0, color: "FFFFFF" }, left: { style: BorderStyle.SINGLE, size: 24, color: TEAL } },
      margins: { top: 120, bottom: 120, left: 200, right: 160 },
      children: lines.map(l => new Paragraph({ children: rich(l, { size: 19 }), spacing: { after: 60, line: 290 } })),
    })] })],
  });
}

// ---------- content ----------
const c = [];

// Cover / summary
c.push(new Paragraph({ children: [t("제주 AI·빅데이터 활용 AI Agent 개발 챌린지 · AI Agent 기획서", { size: 18, color: GRAY })], spacing: { after: 200 } }));
c.push(new Paragraph({ children: [t("제주 데이터 관제실", { size: 44, bold: true, color: NAVY })], spacing: { after: 80 } }));
c.push(new Paragraph({ children: [t("관광·교통 이상 신호 탐지·원인 설명 AI Agent", { size: 28, color: TEAL, bold: true })], spacing: { after: 160 } }));
c.push(new Paragraph({ border: { bottom: { style: BorderStyle.SINGLE, size: 8, color: NAVY, space: 4 } }, children: [t("팀 숨비소리  |  팀장 nnin (Data Scientist) · 팀원 hjshin93 (Data Analyst)  |  2026.11", { size: 18, color: GRAY })], spacing: { after: 240 } }));
c.push(callout([
  "**한 줄 정의** — 제주데이터허브의 유동인구·버스·와이파이 데이터를 일 단위로 살펴 **평소와 다른 날과 지역**을 찾고, 같은 날 다른 지표의 변화와 기상·공휴일·행사를 대조해 **무엇이, 어디서, 얼마나, 왜(후보)** 달라졌는지 근거·출처·확신도와 함께 알려주는 AI Agent",
  "**누가 쓰나** — 제주빅데이터센터를 찾는 기관·사업자(관광·교통 담당 공무원, 관광사업자, 연구자)의 정례 모니터링과 현황자료 작성",
  "**무엇이 다른가** — 계산은 코드가, 설명은 LLM이 맡고, **검증기를 통과한 숫자와 근거만** 보고합니다. 원인을 정해 둔 가짜 이상을 데이터에 넣어 탐지·원인 설명 성능을 **수치로 평가**합니다.",
]));
c.push(gap(160));
c.push(table([2400, 7238], ["항목", "요약"], [
  ["필수 데이터", "제주데이터허브 Open API 13종(유동인구·버스·와이파이·기상·입도객 등) + 파일 1종(축제·행사)"],
  ["Agent 구성", "Planner(LLM, 도구 호출) → 도구 7종(시계열·이상 탐지·동반 변화·맥락 대조·문서 검색·차트·브리핑) → 검증기 → 브리핑"],
  ["주 분석 기간", "2024-04-01 ~ 2025-03-31 (모든 신호가 허브 데이터로 겹치는 1년) + 최근 모니터링(버스·와이파이 ~2026-11)"],
  ["실행 환경", "센터 PC(Windows 11, i7-8700, RAM 32GB)에서 로컬 서버 + 브라우저, GPU 불필요, 외부 LLM 차단 시 오프라인 모드"],
  ["평가 지표", "이상 탐지 정밀도·재현율, 원인 Top-3 정확도, 숫자 일치율, 출처 정확도, 질문당 비용"],
], { firstColShade: true }));
c.push(gap(120));
c.push(TODO("평가 결과 핵심 수치 3개(탐지 재현율, 원인 Top-3 정확도, 숫자 일치율) — 11/17 측정 후 표지에 기재"));
c.push(BR());

// 1. 구현 목표
c.push(H1("1. 구현 목표"));
c.push(H2("1.1 문제"));
c.push(P("제주의 관광·교통 현장은 날씨, 연휴, 행사, 항공·선박 사정에 따라 하루 단위로 크게 출렁입니다. 기관 담당자는 \"지난주 왜 이 지역 방문객이 늘었지?\", \"이번 달 평소와 달랐던 곳은 어디지?\"를 확인하려면 여러 데이터를 찾아 내려받고, 기간을 맞추고, 비교 기준을 세워야 합니다. 데이터는 제주데이터허브에 공개되어 있지만, **어떤 데이터를 어떻게 결합해야 하는지**와 **무엇을 '평소와 다르다'로 볼지**를 정하는 데 전문 지식과 시간이 듭니다."));
c.push(H2("1.2 분석 주제"));
c.push(P("**제주 관광·교통 일 단위 신호의 이상 탐지와 원인 후보 설명.** 읍면동 유동인구, 장소별 공공와이파이 이용, 정류소별 버스 이용을 하나의 \"관제판\"으로 묶고, 계절·요일 패턴으로 만든 기준선에서 크게 벗어난 날과 지역을 찾습니다. 찾은 이상마다 같은 날 같은 지역의 다른 신호, 기상, 공휴일, 행사, 입도객 변화를 대조해 원인 후보를 근거와 함께 제시합니다."));
c.push(H2("1.3 AI를 활용한 데이터 분석 목표"));
c.push(table([2300, 7338], ["목표", "내용"], [
  ["탐색 자동화", "자연어 질문만으로 필요한 데이터·지역·기간을 Agent가 고르고 계산까지 수행"],
  ["이상 탐지", "기준선 대비 잔차로 이상일·이상 지역을 찾고, 방법 2개를 비교해 더 나은 방법을 기본값으로 사용"],
  ["원인 설명", "동반 변화·기상·공휴일·행사를 대조해 원인 후보를 확신도와 함께 제시(원인 단정 금지)"],
  ["신뢰성", "모든 숫자·근거를 검증기가 도구 결과와 대조, 출처(데이터명·기간·API) 자동 표기"],
  ["정량 목표", "가짜 이상 주입 평가에서 탐지 재현율 0.8 이상, 원인 Top-3 정확도 0.7 이상, 숫자 일치율 100% (목표치이며 결과는 6장에 기재)"],
], { firstColShade: true }));
c.push(BR());

// 2. 차별점
c.push(H1("2. 기존 사례와 차별점"));
c.push(P("제주 지역에서 열린 데이터 대회 수상작과 비교하면, 지금까지는 **예측 정확도 경쟁**이나 **관광객·소상공인용 앱**이 중심이었습니다. 기관이 정례 모니터링에 쓰는 **탐지→원인 설명→검증** Agent는 확인되지 않았습니다."));
c.push(table([3000, 3300, 3338], ["기존 사례", "성격", "본 과제"], [
  ["DACON×제주테크노파크 대회(퇴근시간 버스 승차인원·버스 운행시간·도로 교통량·특산물 가격 예측)", "예측 모델 정확도 경쟁", "예측은 기준선으로만 쓰고, 기준선을 벗어난 날의 원인을 설명"],
  ["2023 제주 스마트관광 빅데이터 해커톤 「제주여행객 맞춤형 버스노선 추천 서비스」(장려상)", "관광객 대상 추천 앱", "기관 대상 모니터링·현황자료 작성 도구"],
  ["제주 공공데이터·AI 활용 창업경진대회 대상(2025 동적 가격 「PRICE Lab in Jeju」, 2026 「제주 로컬타임 AI」)", "소상공인·관광객 서비스", "센터에 탑재해 방문 기관이 직접 실행"],
  ["일반 LLM 데이터 요약", "숫자 환각 위험", "계산은 코드, 검증기 통과 결과만 출력, 성능을 수치로 공개"],
]));
c.push(gap(80));
c.push(P("참고: 2026 한국관광 데이터랩 경진대회 최우수작(김포시)은 방문자 유입·승하차·BIS 데이터로 관광지 대중교통 노선을 단계적으로 구축했습니다. 관광 수요 변화를 데이터로 빠르게 읽는 일이 실제 정책 수요임을 보여 주며, 본 과제는 그 첫 단계인 \"변화 감지와 원인 파악\"을 자동화합니다.", { color: GRAY }));
c.push(BR());

// 3. 서비스 제안
c.push(H1("3. 서비스 제안"));
c.push(H2("3.1 데이터 활용 개요"));
c.push(P("허브의 일 단위 신호 3종(읍면동 유동인구, 장소별 와이파이 이용, 정류소별 버스 이용)을 **신호**로, 기상·공휴일·행사·입도객을 **맥락**으로, 와이파이 AP 위치·정류소 좌표를 **위치 연결 고리**로 씁니다. 신호를 읍면동 단위로 맞추면 \"같은 날 같은 곳에서 여러 신호가 함께 움직였는가\"를 볼 수 있고, 이것이 원인 설명의 핵심 근거가 됩니다."));
c.push(H2("3.2 핵심 기능"));
c.push(table([2300, 7338], ["기능", "설명"], [
  ["① 이상 신호 찾기", "\"2025년 1월에 평소와 달랐던 지역은?\" → 지역·날짜·신호별 이상 목록과 크기(기준선 대비 %)"],
  ["② 원인 후보 설명", "\"애월읍 방문인구가 왜 늘었어?\" → 동반 변화·기상·공휴일·행사를 대조한 원인 후보, 근거, 확신도(상·중·하)"],
  ["③ 정례 브리핑", "\"이번 분기 이상 신호 브리핑\" → 표·차트·서술·출처가 담긴 HTML 브리핑, 현황자료에 바로 인용"],
  ["④ 데이터 설명", "\"이 숫자는 어디서 왔고 어떻게 계산했어?\" → 데이터 명세·API 문서를 검색해 출처와 함께 답변(RAG)"],
], { firstColShade: true }));
c.push(H2("3.3 사용자 시나리오"));
c.push(B("**관광 담당 공무원(월간 브리핑)**: 매월 초 \"지난달 이상 신호 브리핑\"을 요청 → 이상 지역 5곳과 원인 후보를 받고, 근거 표를 내부 보고서에 붙여 넣음"));
c.push(B("**교통 담당자(이상일 조사)**: \"설 연휴 성산읍 버스 승차가 평소보다 얼마나 늘었고, 와이파이 이용도 같이 늘었나?\" → 수치·차트·동반 변화 확인 후 증차 검토 자료로 활용"));
c.push(H2("3.4 편의성"));
c.push(B("SQL·코딩 없이 한국어 질문만으로 사용, 질문 예시 버튼 제공"));
c.push(B("모든 답에 데이터 기준일·출처·계산 방법을 자동 표기 → 보고서에 그대로 인용 가능"));
c.push(B("원인은 \"후보 + 근거 + 확신도\"로 제시해 과도한 해석을 막음"));
c.push(B("외부 LLM을 쓸 수 없는 환경에서도 표·차트·템플릿 문장으로 동작(오프라인 모드)"));
c.push(H2("3.5 분석 데이터 활용 방안(센터 활용)"));
c.push(B("센터 PC에 탑재해 방문 기관이 자기 지역·기간을 지정해 셀프 분석"));
c.push(B("센터 정례 리포트(월간 \"제주 이상 신호 브리핑\") 초안 자동 생성"));
c.push(B("확장: 센터 제공 데이터(카드 이용·외식업 POS CSV)를 같은 탐지·설명 구조에 연결, 반출 기준(10 미만 값·역산) 검사 포함"));
c.push(BR());

// 4. Agent 개발 구성
c.push(H1("4. Agent 개발 구성"));
c.push(H2("4.1 참여자의 역할과 목표"));
c.push(table([2000, 1700, 5938], ["참여자", "역할", "담당"], [
  ["nnin (팀장)", "Data Scientist", "이상 탐지 방법 설계·비교, Agent(도구 호출 루프·RAG·검증기) 구현, 평가 설계·실행, 개발·탑재"],
  ["hjshin93", "Data Analyst", "허브 데이터 수집 결과 점검, 위치 매핑 검수, 실제 이상 사례 검토·해석, 기획서·결과 설명자료 작성"],
], { firstColShade: true }));
c.push(H2("4.2 Workflow"));
c.push(new Paragraph({ alignment: AlignmentType.CENTER, children: [new ImageRun({ type: "png", data: fs.readFileSync(IMG), transformation: { width: 600, height: 340 } })], spacing: { after: 80 } }));
c.push(P("① Planner가 질문을 해석해 데이터·지역·기간을 정하고 도구를 순서대로 호출 → ② 도구는 로컬 캐시와 문서 색인에서 계산·검색하고 결과에 고유 id를 붙여 반환 → ③ Briefing Writer는 결과 id만 참조해 서술 → ④ Verifier가 숫자·출처·근거를 대조, 실패 시 Planner에 오류를 돌려보내 재계획(최대 2회) → ⑤ 통과한 브리핑만 사용자에게 표시", { size: 18 }));
c.push(H2("4.3 Tool / API"));
c.push(table([2300, 3700, 3638], ["도구", "입력 → 출력", "구현"], [
  ["get_series", "신호, 지역, 기간 → 일 단위 시계열", "로컬 캐시(DuckDB) 조회"],
  ["detect_anomalies", "시계열, 방법 → 이상일 목록(값·기대값·점수·방향)", "계절·요일 기준선 대비 잔차 점수 / 로버스트 잔차, 2방법 비교"],
  ["find_co_movements", "날짜, 지역 → 같은 날 함께 움직인 신호", "신호별 점수 동시 비교"],
  ["check_context", "날짜, 지역 → 기상·공휴일·행사·입도객", "허브 기상·입도객 API, 공휴일 라이브러리, 행사 CSV"],
  ["search_docs", "질문 → 문서 조각(출처 위치 포함)", "BM25 + 다국어 임베딩 비교(RAG)"],
  ["make_chart", "결과 id → 차트", "Plotly"],
  ["draft_briefing", "결과 id 목록 → 브리핑 초안", "LLM, 숫자는 id 참조만 허용"],
]));
c.push(H2("4.4 사용 모델"));
c.push(B("**LLM**: 외부 API의 도구 호출 지원 모델(공급자 교체 가능 구조). 모델·버전은 11/11 비용·성능 비교 후 확정해 최종 결과물에 명시"));
c.push(B("**이상 탐지**: 통계 기반 기준선 모델(계절·요일 분해, 로버스트 잔차) — GPU 불필요"));
c.push(B("**검색(RAG)**: BM25 기본, 다국어 소형 임베딩 모델(CPU)과 비교해 성능이 좋은 쪽 사용"));
c.push(B("**선택**: 외부 LLM 차단 시 소형 로컬 LLM(CPU)으로 검증된 숫자만 문장화 — 품질 측정 후 포함 여부 결정"));
c.push(H2("4.5 판단 및 자율 수행 범위"));
c.push(table([2000, 7638], ["구분", "범위"], [
  ["자율 수행", "질문 해석, 데이터·지역·기간 선택, 도구 호출 순서 결정, 탐지·대조 계산, 검증 실패 시 재계산·범위 축소(최대 2회), 브리핑 작성"],
  ["사용자 확인", "데이터가 없는 기간·지역 요청 시 대안 기간 제시 후 선택 요청, 결과 저장 여부(삭제 ON/OFF)"],
  ["하지 않음", "원인 단정(\"~때문\" 대신 후보·근거·확신도), 검증 안 된 숫자 출력, 센터 원본 데이터의 외부 전송, 데이터 범위 밖 추정(실시간 정보 등)"],
], { firstColShade: true }));
c.push(BR());

// 5. 데이터 활용 계획
c.push(H1("5. 데이터 활용 계획"));
c.push(H2("5.1 필수 데이터"));
c.push(P("모두 제주데이터허브 공개 데이터이며, 데이터 상세 페이지·API 미리보기·API 기술문서로 필드와 수록 기간을 확인했습니다(2026-11-10).", { size: 18, color: GRAY }));
c.push(table([950, 2450, 3450, 1550, 1238], ["ID", "데이터명", "활용 항목", "확인된 최신일", "용도"], [
  ["583", "읍면동 단위 내국인 유동인구", "날짜, 시군구, 읍면동, 성별, 연령대, 거주·근무·방문인구", "2026-08-31", "신호"],
  ["589", "읍면동 외국인 단기체류 유동인구", "날짜, 국가, 읍면동, 방문자수", "2026-08-31", "신호(선택)"],
  ["593", "와이파이 AP그룹별 일일 사용량", "AP그룹명, 날짜, 이용자수, 사용량", "2026-11-05", "신호"],
  ["613", "일일 정류소별 버스 이용자 정보", "날짜, 정류소ID·명, 승차/환승, 요금제, 이용자수", "2026-11-06", "신호"],
  ["617·586", "버스 일일 승객수 / 와이파이 일일 사용자수", "날짜, 이용자수", "2026-11", "전체 추세"],
  ["618", "제주 공공와이파이 AP 정보", "AP그룹명, 카테고리(관광지·해변·올레 등), 주소, 위경도", "자동 갱신", "위치 연결"],
  ["612·611", "버스 정류소 / 노선 기본 정보", "정류소ID, 주소, 위경도 / 노선 정보", "자동 갱신", "위치 연결"],
  ["579·578", "일별 기상 정보 / 기상관측소 정보", "관측소, 기온, 강수량, 풍속 / 관측소 위경도", "2025-03 무렵", "맥락"],
  ["580·582", "방문목적별·국가별 입도객", "연월, 목적·국가, 방문자수", "2025-07", "맥락"],
  ["761", "VISIT JEJU 축제행사콘텐츠(File)", "행사명, 시작·종료일, 주최", "2025-09 등록", "맥락"],
]));
c.push(H2("5.2 수집·전처리"));
c.push(B("허브 Open API(프로젝트키, 페이지당 최대 100행, 데이터별 일일 1,000회)로 수집, 쿼터 소진 시 중단 지점부터 이어받기"));
c.push(B("**주 분석 기간 2024-04-01 ~ 2025-03-31**: 허브 기상 API가 2025년 봄까지 제공되어, 이 기간이면 모든 신호·맥락이 허브 데이터로 겹침. 쿼터를 고려해 와이파이 AP그룹은 6개월(2024-10~2025-03), 정류소별 버스는 3개월(2025-01~03, 승차·일반·카드) 수집"));
c.push(B("최근 모니터링: 버스·와이파이 ~2026-11, 유동인구 ~2026-08 (기상 맥락 없이 제공)"));
c.push(B("정제: 읍면동 명칭 정규화(예: \"성산\"→\"성산읍\"), 유동인구는 성별·연령 합산, 결측일은 이상으로 보지 않도록 별도 표시"));
c.push(B("수집본은 DuckDB/parquet 캐시로 저장해 결과물 ZIP에 포함(허브 공개 데이터, 출처·전처리 내용 명세)"));
c.push(H2("5.3 결합 방법"));
c.push(B("와이파이: AP그룹명 → AP 정보(카테고리·위경도) → 읍면동. 관광지·해변·올레코스 카테고리는 \"관광 장소 신호\"로 따로 집계"));
c.push(B("버스: 정류소ID → 정류소 기본 정보(위경도·주소) → 읍면동"));
c.push(B("기상: 읍면동 중심과 가장 가까운 관측소 매핑 / 행사: 장소 정보가 없어 주요 행사만 읍면동을 직접 지정하고 출처 표기"));
c.push(B("매칭 실패 건수는 숨기지 않고 데이터 품질 지표로 보고"));
c.push(H2("5.4 이용조건과 보안"));
c.push(B("허브 공개 데이터는 「공공데이터의 제공 및 이용 활성화에 관한 법률」에 따라 출처 표기 후 활용"));
c.push(B("허브 API 키는 결과물에 넣지 않고 발급·설정 방법만 매뉴얼에 기재(.env 예시 파일)"));
c.push(B("대회 제공 허브 데이터 목록 파일은 결과물·외부 저장소에 포함하지 않음"));
c.push(B("개인 단위 데이터 없음(유동인구·이용자 수는 집계값). 센터 데이터 연동 시 반출 기준(10 미만·역산 가능 값) 검사 후에만 외부 LLM에 전달"));
c.push(BR());

// 6. 검증·평가
c.push(H1("6. 검증 방법과 평가"));
c.push(H2("6.1 가짜 이상 주입 평가"));
c.push(P("실제 이상에는 정답이 없으므로, 실제 시계열의 특정 날짜·지역에 **크기(기준선 대비 2~6배 표준편차)와 원인 유형(기상 연동, 행사, 여러 신호 동반)을 정해 둔 가짜 이상**을 넣어 정답이 있는 평가 세트를 만듭니다. Agent가 이를 찾고 원인을 맞히는지 측정합니다."));
c.push(H2("6.2 지표"));
c.push(table([2600, 4400, 2638], ["지표", "정의", "목표"], [
  ["탐지 정밀도·재현율", "주입한 이상을 찾은 비율 / 찾은 것 중 실제 주입 비율", "재현율 0.8 이상"],
  ["원인 Top-3 정확도", "정답 원인이 제시한 후보 3개 안에 든 비율", "0.7 이상"],
  ["숫자 일치율", "브리핑 숫자가 도구 계산값과 일치하는 비율", "100%"],
  ["출처 정확도", "인용한 문장이 실제 문서·데이터에 있는 비율", "95% 이상"],
  ["범위 밖 질문 처리", "데이터 없는 기간·실시간 질문에 올바르게 안내한 비율", "100%"],
  ["질문당 지연·비용", "응답 시간, LLM API 비용", "측정·공개"],
]));
c.push(H2("6.3 비교 실험"));
c.push(B("이상 탐지 방법 2개 비교 → 성능이 좋은 방법을 기본값으로"));
c.push(B("검증기 켜기/끄기 → 잘못된 숫자·근거가 사용자에게 도달하는 비율 비교"));
c.push(B("RAG 검색 BM25 vs 임베딩 → 출처 정확도 비교"));
c.push(H2("6.4 결과"));
c.push(TODO("지표별 측정값 표, 비교 실험 결과, 실제 사례 2~3건(공휴일·기상 등 데이터로 확인되는 경우만) — 11/17 평가 후 기재. 목표 미달 항목도 그대로 공개"));
c.push(BR());

// 7. 개발·탑재 계획
c.push(H1("7. 개발·탑재 계획"));
c.push(H2("7.1 구현 범위"));
c.push(table([1500, 8138], ["구분", "범위"], [
  ["필수", "허브 수집·캐시, 위치 매핑, 이상 탐지(2방법), 원인 대조, RAG, 도구 호출 Agent, 검증기, HTML 브리핑, 웹 UI, 평가 스크립트, 오프라인 모드"],
  ["선택", "최근 모니터링 화면, 외국인 유동인구, 소형 로컬 LLM, 외부 기상 API 연동(최근 기간), 센터 CSV 업로드·반출 기준 검사"],
], { firstColShade: true }));
c.push(H2("7.2 기술 환경"));
c.push(table([2300, 7338], ["항목", "내용"], [
  ["언어·런타임", "Python 3.11 (Windows 11 기준 검증)"],
  ["주요 라이브러리", "pandas, DuckDB, statsmodels(계절 분해), rank-bm25, sentence-transformers(선택), holidays, Plotly, Streamlit(UI, 11/11 확정), pytest"],
  ["LLM", "외부 API(도구 호출 지원), 공급자 추상화 계층 — 모델명·버전은 최종 결과물에 명시"],
  ["데이터 저장", "로컬 DuckDB/parquet 캐시(ZIP 포함)"],
], { firstColShade: true }));
c.push(H2("7.3 UI 구성"));
c.push(B("**질문 화면**: 질문 입력창, 예시 질문 버튼, 기간·지역 필터"));
c.push(B("**결과 화면**: 이상 목록 표, 신호 차트(기준선·이상일 표시), 원인 후보 카드(근거·확신도), 출처 목록"));
c.push(B("**브리핑 화면**: HTML 브리핑 미리보기·저장(저장 시 삭제 ON/OFF 설정)"));
c.push(B("1920×1080, Chrome·Edge 기준 레이아웃"));
c.push(H2("7.4 센터 실행환경과 외부 서비스 의존성"));
c.push(table([3000, 6638], ["항목", "대응"], [
  ["센터 PC 사양(i7-8700, GTX 1060, RAM 32GB)", "GPU 불필요, 통계 모델과 CPU 검색만 사용"],
  ["설치", "센터 담당자가 따라 할 수 있는 단계별 설치 매뉴얼, 인터넷 설치 + 오프라인 설치 파일 목록 제공"],
  ["실행 방식", "로컬 서버(127.0.0.1) + 브라우저"],
  ["외부 접속 주소", "open.jejudatahub.net(허브 Open API, 데이터 갱신 시), LLM API 주소 1곳(모델 확정 후 기재) — 허용 목록 등록 요청"],
  ["보안 정책(DLP)", "외부 LLM에는 집계값과 질문만 전송, 차단 시 오프라인 모드로 자동 전환"],
  ["결과 보존", "결과 저장 기능에 삭제 ON/OFF, 보존 대상·이유를 매뉴얼에 명시"],
  ["운영 비용", "질문당 LLM 비용을 측정해 기재, 결과 캐시로 반복 질문 비용 절감"],
], { firstColShade: true }));
c.push(H2("7.5 일정"));
c.push(table([1500, 5638, 2500], ["날짜", "작업", "담당"], [
  ["11/11", "허브 수집 시작, LLM·UI 확정", "nnin / 수집 점검 hjshin93"],
  ["11/12~13", "위치 매핑·이상 탐지·원인 대조, RAG 색인", "nnin / 매핑 검수 hjshin93"],
  ["11/14~15", "Agent 루프, 검증기, 브리핑", "nnin"],
  ["11/16", "UI, 오프라인 모드", "nnin / 실제 사례 검토 hjshin93"],
  ["11/17", "평가 실행, 비용 측정", "nnin / 결과 해석 hjshin93"],
  ["11/18", "기획서 확정, 매뉴얼", "hjshin93 / 검토 nnin"],
  ["11/19", "설치 재현, ZIP 구성, 제출(팀장)", "공동"],
]));
c.push(BR());

// 8. 한계
c.push(H1("8. 한계와 대응"));
c.push(table([3200, 6438], ["한계", "대응"], [
  ["동반 변화·맥락은 상관관계이며 인과가 아님", "\"원인 후보 + 근거 + 확신도\"로만 표현, 브리핑에 한계 문구 고정"],
  ["허브 기상 API가 2025년 봄에 끊김", "주 분석 기간을 2024-04~2025-03으로 설정, 최근 기간은 기상 없이 제공(외부 기상 API는 선택 확장)"],
  ["유동인구는 약 2개월 늦게 갱신, 값은 하루 시간대별 인구의 합", "데이터 기준일 자동 표기, 단위 설명을 결과에 포함"],
  ["행사 데이터에 장소 정보가 없음", "주요 행사만 지역 직접 지정, 행사는 원인 후보의 일부로만 사용"],
  ["API 쿼터(데이터별 일 1,000회)", "기간을 나눠 수집, 캐시 제공으로 평가·운영 시 재호출 불필요"],
  ["가짜 이상 주입 평가는 실제 이상의 다양성을 다 담지 못함", "실제 사례 정성 검토를 함께 제시"],
], { firstColShade: true }));
c.push(gap(160));

// 9. 기대 효과
c.push(H1("9. 기대 효과와 확장"));
c.push(B("**기관**: 현황자료 작성 전 \"무엇이 달라졌는지\" 확인 시간을 줄이고, 근거·출처가 붙은 수치를 보고서에 바로 인용"));
c.push(B("**센터**: 방문자 셀프 분석 도구, 월간 이상 신호 브리핑 정례화"));
c.push(B("**확장**: 센터 카드·POS CSV 연동(반출 기준 검사 포함), 외부 기상 API로 최근 기간 맥락 보강, 이상 발생 알림"));
c.push(gap(160));
c.push(H2("부록. 출처"));
c.push(P("제주데이터허브(jejudatahub.net) 데이터 상세 페이지·API 기술문서, 대회 게시판 공식 답변(2026-10~11), DACON 제주 대회 페이지, 시사매일(2026.08.06), 코리아타임뉴스(2025.08.06), 일간투데이(김포시 사례). 2023 해커톤 수상작은 검색 요약 기준이며 기사 원문은 확인하지 못함.", { size: 17, color: GRAY }));

// ---------- document ----------
const doc = new Document({
  creator: "숨비소리",
  title: "제주 데이터 관제실 AI Agent 기획서",
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
    { reference: "num", levels: [ { level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 360, hanging: 300 } } } } ] },
  ] },
  sections: [{
    properties: { page: { size: { width: 11906, height: 16838 }, margin: { top: 1134, bottom: 1134, left: 1134, right: 1134 } } },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [
      new TextRun({ text: "숨비소리 · 제주 데이터 관제실 기획서  |  ", font: FONT, size: 16, color: GRAY }),
      new TextRun({ children: [PageNumber.CURRENT], font: FONT, size: 16, color: GRAY }) ] })] }) },
    children: c,
  }],
});
Packer.toBuffer(doc).then(buf => { fs.writeFileSync(OUT, buf); console.log("written", OUT); });
