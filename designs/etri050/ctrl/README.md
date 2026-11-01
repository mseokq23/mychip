# 제어 블록 teg_ctrl

PDK 모델 검증용 온칩 특성화 IC의 디지털 제어부다. 스캔으로 설정을 받아 측정 블록 하나(Kelvin 어레이, CBCM, RO 뱅크)만 켜고, 출력 핀 하나로 스캔 읽기 또는 RO 주파수 ÷256을 내보낸다. 킷 표준셀(khu_etri050)로 합성하고 qflow로 배치·배선한다(FIR_PE MPW240925002와 같은 흐름).

```
teg_ctrl/teg_ctrl.v     RTL
tb/tb_teg_ctrl.v        자체 판정 테스트벤치 (RTL과 게이트 수준 넷리스트에 같은 것을 씀)
cell_area.py            게이트 넷리스트의 셀 수와 LEF 면적 합
layout/teg_ctrl.cel2    qflow 핀 배치 힌트 (변별 핀 묶음, 위 변 구간)
run_flow.sh             qflow 배치·배선 + 킷 DRC·LVS·스택 비아 검사 + 평탄화 DRC·공식 규칙 KLayout DRC(같은 넷 홈을 메운 사본 포함)
strip_port_wires.py     qflow 넷리스트의 중복 포트 선언을 빼서 Icarus로 시뮬레이션하게 함
Makefile                sim / synth / gatesim / flow / qflowsim
```

## 레지스터

`sck` 상승 에지마다 `sdi`를 20비트 시프트 레지스터에 넣는다(MSB 먼저, 처음 넣은 비트가 sr[19]). `sle` 상승 에지에서 섀도 레지스터로 복사되어 디코더를 구동한다. 시프트 중에도 섀도 레지스터는 그대로라 측정 상태가 흔들리지 않는다.

| 비트 | 이름 | 뜻 |
|---|---|---|
| [1:0] | mode | 00 꺼짐, 01 Kelvin 어레이, 10 CBCM, 11 RO |
| [5:2] | row | 어레이 행 0–11 (12–15는 선택 없음) |
| [8:6] | col | 어레이 열 0–7 |
| [12:9] | cbsel | CBCM 셀 0–9 (10–15는 선택 없음) |
| [15:13] | rosel | RO 0–5 (6, 7은 선택 없음) |
| [16] | osel | 0: out = 스캔 읽기(sr[19]), 1: out = RO ÷256. 0이면 분주기를 리셋 |
| [19:17] | — | 예비 |

출력: `row_sel/row_selb`(12), `col_sel/col_selb`(8) — 어레이 TG용 양극성, `cbcm_en`(10), `cbcm_clk`(= cck · mode10), `ro_en`(6), `out`. 입력 `ro_in`(6)은 각 RO의 탭.

## 검증

```bash
cd designs/etri050/ctrl
make sim       # RTL: TB RESULT: PASS (157 checks)
make synth     # Yosys + 킷 liberty → build/teg_ctrl_syn.v, build/area.txt
make gatesim   # 합성 넷리스트 + 킷 셀 모델(khu_etri05_stdcells.v): TB RESULT: PASS (157 checks)
```

테스트벤치가 보는 것: 어레이 128가지(행 16 × 열 8, 행 12–15는 선택 없음), CBCM 16가지, RO 8가지, mode 00, 스캔 읽기(다음 설정을 넣으면서 이전 설정이 그대로 나옴), 분주기(OUT 주기 = 선택한 RO 256주기, 다른 RO는 OUT에 영향 없음). 일부러 넣은 오류(행 디코드 어긋남, CBCM 클록 게이트 제거, 섀도 비트 누락, ÷128 분주)는 모두 FAIL로 잡힌다.

합성 결과(Yosys 0.70, 킷 liberty, 킷 커밋 111dc09): 셀 177개 — DFFPOSX1 37, DFFSR 8(분주기), 조합 132. LEF 크기 합 0.127 mm²(배치 밀도 100% 기준, 배선·필러 제외). qflow 합성은 버퍼 삽입 등으로 수가 조금 다를 수 있다. Codespace(Yosys 0.70, Icarus Verilog 14.0, 킷 db09a3d)에서도 `make all` 결과가 같다(RTL·게이트 모두 PASS 157, 177셀, 0.1270 mm², 2026-11-01).

## 배치·배선 (qflow)

```bash
make flow      # = bash run_flow.sh → build/qflow/flow_summary.txt
make qflowsim  # qflow가 합성한 넷리스트(배치·배선에 들어간 것)에 같은 테스트벤치
```

- 킷 `scripts/RTL_Project/ETRI050/Makefile`과 같은 순서: `qflow synthesize → place → sta → route → migrate → lvs`, 이어서 킷 `run_drc.sh`, `run_lvs.sh`, `check_via_stack.py`. 그 뒤 세 가지를 더 본다: 킷 `mag2gds.sh`로 평탄화한 `teg_ctrl_F`의 Magic DRC, 그 ETRI GDS에 킷의 공식 규칙 변환 덱(KLayout) 검사(`scripts/lyrdb_summary.py`로 규칙별 개수·간격 요약), 금속2·3 도형 안의 좁은 홈을 메운 사본(`scripts/fill_notches.py` → `teg_ctrl_F_fill.gds`)에 같은 덱 검사.
- qflow 기술 디렉터리는 `build/qflow/tech/etri050`에 만든다. 킷 파일을 `tech/etri050.sh`가 기대하는 이름으로 연결한다(예: `khu_etri05_stdcells.lib` → `etri05_stdcells.lib`). 킷의 `project_vars.sh`와 GrayWolf 템플릿(`TOP_MODULE.par`)을 쓰되, 템플릿에서 코어 높이/폭 비(`TWMC*chip.aspect.ratio`, 템플릿 1.0)만 0.49로 바꾼다(배치도 칸에 맞추기, 아래 결과). `ASPECT=0.37 make flow`처럼 바꿔 돌릴 수 있다.
- 필요한 도구: qflow, yosys, graywolf, qrouter, magic, netgen, tcsh, klayout, python3. 하나라도 없으면 시작 전에 이름을 알려 주고 멈춘다.
- Codespace 이미지에는 yosys·magic·netgen만 있고 qflow·graywolf·qrouter·tcsh가 없다(2026-11-01 확인). `designer` 계정의 sudo는 비밀번호를 요구해 apt로 설치할 수 없으므로, `bash scripts/install-qflow-etri050.sh`가 루트 없이 `~/.local/etri050-tools`에 설치한다: tcsh(우분투 패키지를 풀어 씀), graywolf(킷 `Tools/graywolf_build.sh`와 같은 저장소), qrouter 1.4.88(킷 pong_pt1 MPW2025 레이아웃에 기록된 판), 킷의 `qflow-1.4.100_etri050.tar.gz`. 킷 qflow 압축본은 qflow 1.4.100(커밋 b0f76bf)에 `tech/etri050` 추가와 파이썬 정규식 수정만 더한 것이다.
- 핀 변: 스캔 입출력은 아래(남쪽 패드), 어레이·RO 선택은 위, CBCM 선택은 오른쪽(칩 배치도 기준). 위 변에는 구간 힌트를 준다(어레이 선택 `sidespace 0.0 0.6`, RO `0.62 0.98`, 왼쪽 끝부터의 비율). GrayWolf·qflow 소스상 이 힌트와 핀 간격 정리(qflow `arrangepins.tcl`, 2트랙 = 6 µm)는 핀을 블록 끝에 묶어 두지 않으므로, 결과 핀 위치를 매번 확인한다.
- 기술 디렉터리의 링크는 킷 `Tools/qflow-1.4.100_etri050_build.sh`와 같다. 그래서 qflow가 `layout/.magicrc`로 복사하는 파일이 킷 템플릿의 `layout/.magicrc`(= `digital_ETRI/khu_etri050.magicrc`)와 같다.

### 결과 (2026-11-01, Codespace, 킷 db09a3d)

도구: 킷 qflow 1.4.100, graywolf 0.1.6-4-gf47937b(자체 테스트 6개 중 5개 통과 — 전체 배치 흐름 시험 2개와 TimberWolfSC 시험은 기대 파일과 바이트 단위로 같고, 실패 1개는 TimberWolfMC 단독 시험에서 패드 위치가 기대 파일과 다름), qrouter 1.4.88, Yosys 0.70, Magic 8.3.685, Icarus Verilog 14.0. 한 번 실행에 약 22 s(홈 메우기와 두 번째 KLayout 검사 포함).

| 항목 | 결과 |
|---|---|
| 블록 크기 | 603.9 × 301.1 µm(0.182 mm², 핀 포함), 코어 582 × 288 µm = 8행 × 36 µm |
| 셀 | 255개(필러 포함), 셀 면적 합 0.1676 mm² = 코어 면적(행이 필러까지 꽉 참). qflow가 팬아웃 버퍼 BUFX2 58·CLKBUF1 8개를 넣는다 |
| 배선 | `Final: No failed routes!` |
| qflow LVS | Circuits match uniquely, 넷·소자·핀·속성 불일치 없음 |
| 킷 LVS (`run_lvs.sh`) | `Final result: Circuits match uniquely.` |
| 킷 DRC (`run_drc.sh`) | `Total DRC errors found: 0`. 표시 타일 9개는 모두 "This layer can't abut or partially overlap between subcells" |
| 평탄화 DRC (`teg_ctrl_F`) | `No errors found.` |
| 스택 비아 | `No stacked Contact and/or Via found.` |
| qflow 넷리스트 시뮬레이션 (`make qflowsim`) | `TB RESULT: PASS (157 checks)` |
| KLayout 공식 규칙 변환 덱 | 284개: 10.MET2.S1 250(간격 0.9 µm 210, 0.8 µm 40), 12.MET3.S1 34(0.9 µm). 모두 한 금속 도형 안의 홈(같은 넷) — 아래 "공식 규칙과 다른 점" |
| 홈을 메운 사본 (`teg_ctrl_F_fill.gds`) | 금속2 홈 242곳(92.7 µm²)·금속3 34곳(12.2 µm²) 메움, 조각 최대 0.90 µm, 도형 수 그대로(885·387). KLayout 공식 규칙 표시 0 |

- 셀 겹침 표시 타일: 킷 연구노트22(탁구 게임기, MPW2025 STD-II)는 "전원선을 공유하도록 표준셀이 겹친 것이라 무시해도 좋다"고 설명하고, 킷 `drc_core.sh`도 이 항목을 `drc ignore`한다. 킷 FIR_PE 최종 코어는 24개, 탁구 게임기는 17개였다. 평탄화하면 사라진다(위 표).
- 핀 위치(블록 좌표, µm): 아래 변(금속2) out 87, cck 528, sle 534, sdi 540, sck 546 / 오른쪽 변(금속3) cbcm_clk 18, cbcm_en[9:0] 195–249 / 위 변(금속2) col_selb·col_sel 6–213, row_selb·row_sel 219–405, ro_en 474–522, ro_in 540–573 / vdd 왼쪽, gnd 오른쪽(금속1). 칩 조립 때 남쪽 패드 순서(SDI, SCK, SLE, OUT, CCK)에 맞춰 아래 변 핀 순서를 다시 정할 수 있다.
- 블록 모양: 높이/폭 비 1.0(킷 템플릿)은 11행 451 × 409 µm, 0.37은 7행 685 × 265 µm, 0.49는 8행 604 × 301 µm. 배치도 칸 x 95–699(PNP2와 CBCM 사이)에 들어가는 것은 0.49다. 이 비가 높이/폭이라는 것은 graywolf `src/twmc/config1.c`(블록 높이 ≈ √(A·비), 폭 ≈ √(A/비))와 실행 결과로 확인했다.
- 첫 실행(비 1.0)에서는 위 변 핀 52개 중 `col_selb[7]`이 블록 밖(x 441 µm > 432 µm)에 놓여 qrouter가 탭을 못 찾았다(배선 실패 1, LVS 핀 오류 1). 넓은 블록과 구간 힌트로 해결했다.

### 공식 규칙과 다른 점 (금속2·3 간격)

- ETRI 설계 규칙 v1.1(docs의 01_NSPL … Design Rule v1.1): 10.MET2.S1, 12.MET3.S1 모두 ≥ 1.0 µm. 킷 LEF(`digital_ETRI/etri050_stdcells.lef`)는 금속2·3 `SPACING 0.9`로 두고 주석에 "ETRI050 Rule: SPACING=1.0"이라 적어 두었다(트랙 3.0 µm, 비아 패드 2.1 µm). Magic 규칙(SCN3ME_SUBM)의 금속2·3 간격은 3λ = 0.9 µm다.
- 표시 284개는 모두 한 금속 도형 안의 홈이다. 같은 배선의 비아 패드 둘(주로 비아1·비아2)이 한 트랙 떨어져 1.05 µm 선으로 이어지면 선 양옆에 0.9 µm 홈이 남는다(0.8 µm는 40곳). KLayout으로 1.0 µm 간격 검사의 변 쌍을 다시 구해 두 변이 같은 도형에 속하는지 보면 모두 같은 도형이다(금속2 242곳, 금속3 34곳). 아래 홈 메우기가 도형을 하나도 잇지 않고 덱 표시를 모두 없애므로, 서로 다른 도형 사이가 1.0 µm보다 좁은 곳은 없다.
- 이 블록이 쓰는 킷 표준셀은 이 규칙을 지킨다: 34종을 킷 GDS 스타일(`lambda=0.30(ETRI)`)로 써서 같은 방식으로 재면 1.0 µm 미만 금속2 간격은 FAX1·HAX1·XNOR2X1·XOR2X1(0.93–0.95 µm)에만 있고, 이 블록은 이 네 셀을 쓰지 않는다(DEF: BUFX2 58, DFFPOSX1 37, INVX1 35, NOR2X1 27, NAND3X1 20, NAND2X1 19, NOR3X1 17, FILL 15, DFFSR 8, CLKBUF1 8, INVX2 5, AOI22X1 3, INVX4·AOI21X1·AND2X2 각 1). Magic 도형(.mag)으로는 20종에 0.9 µm 간격이 있지만, 킷 GDS 스타일이 핀 패드(m2p)와 비아 패드의 바깥 변을 0.05 µm씩 줄이므로 GDS에서는 위 네 셀만 남는다. 블록에서 핀 표시(m2p)를 지우고 GDS를 쓰면 표시가 644개로 는다.
- 제작 선례: 킷의 FIR_PE Rev_E_20240924(MPW240925002로 제작, 킷에 칩 시험 기록 있음) GDS를 같은 방식(1.0 µm 간격 검사)으로 재면 금속2 0.9 µm 2447곳(서로 다른 도형 사이 2127, 한 도형 안 홈 320), 금속3 0.9 µm 364곳(120, 244)이 있다. 0.8 µm는 없다. 킷에 있는 Rev_E(2024-09-19)의 Calibre 결과(`Tutorials_New/4-3_FIR_PE_MPW240925002/FIR_PE_Rev_E/DRC_Results`)에도 10.MET2.S1 1000개 이상(표시 한도, 대부분 0.9 × 2.1 µm 영역)과 12.MET3.S1 318개가 있다.
- 홈 메우기(`scripts/fill_notches.py`): 평탄화 GDS의 금속2·3을 0.49 µm 키웠다 줄여 0.98 µm보다 좁은 틈을 메운다. 메우면 서로 다른 도형이 이어지는 경우에는 출력하지 않고 멈추므로, 한 도형(같은 넷) 안에만 금속을 더한다. 결과는 위 표와 같다(홈 276곳, 공식 규칙 표시 0).
- 배선만 1.0 µm 간격으로 바꿔 시험하면(LEF의 금속2·3 SPACING 1.0, 7행 배치에서 시험) 배선 실패 10, LVS 오류 80으로 3 µm 트랙에서 통과하지 못한다.
- 그래서 배치·배선은 킷 설정 그대로 하고, 칩 조립에는 홈을 메운 GDS를 쓸 수 있다(조립 뒤 GDS 기준 LVS로 다시 확인). ETRI에는 같은 넷 홈 0.8–0.9 µm를 허용하는지 확인한다.
