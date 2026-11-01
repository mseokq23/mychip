# 제어 블록 teg_ctrl

PDK 모델 검증용 온칩 특성화 IC의 디지털 제어부다. 스캔으로 설정을 받아 측정 블록 하나(Kelvin 어레이, CBCM, RO 뱅크)만 켜고, 출력 핀 하나로 스캔 읽기 또는 RO 주파수 ÷256을 내보낸다. 킷 표준셀(khu_etri050)로 합성하고 qflow로 배치·배선한다(FIR_PE MPW240925002와 같은 흐름).

```
teg_ctrl/teg_ctrl.v     RTL
tb/tb_teg_ctrl.v        자체 판정 테스트벤치 (RTL과 게이트 수준 넷리스트에 같은 것을 씀)
cell_area.py            게이트 넷리스트의 셀 수와 LEF 면적 합
layout/teg_ctrl.cel2    qflow 핀 배치 힌트 (변별 핀 묶음)
run_flow.sh             qflow 배치·배선 + 킷 DRC·LVS·스택 비아 검사
Makefile                sim / synth / gatesim / flow
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

- 킷 `scripts/RTL_Project/ETRI050/Makefile`과 같은 순서: `qflow synthesize → place → sta → route → migrate → lvs`, 이어서 킷 `run_drc.sh`, `run_lvs.sh`, `check_via_stack.py`.
- qflow 기술 디렉터리는 `build/qflow/tech/etri050`에 만든다. 킷 파일을 `tech/etri050.sh`가 기대하는 이름으로 연결한다(예: `khu_etri05_stdcells.lib` → `etri05_stdcells.lib`). 킷의 `project_vars.sh`와 GrayWolf 템플릿(`TOP_MODULE.par`)을 그대로 쓴다.
- 필요한 도구: qflow, yosys, graywolf, qrouter, magic, netgen, tcsh. 하나라도 없으면 시작 전에 이름을 알려 주고 멈춘다.
- Codespace 이미지에는 yosys·magic·netgen만 있고 qflow·graywolf·qrouter·tcsh가 없다(2026-11-01 확인). `designer` 계정의 sudo는 비밀번호를 요구해 apt로 설치할 수 없으므로, `bash scripts/install-qflow-etri050.sh`가 루트 없이 `~/.local/etri050-tools`에 설치한다: tcsh(우분투 패키지를 풀어 씀), graywolf(킷 `Tools/graywolf_build.sh`와 같은 저장소), qrouter 1.4.88(킷 pong_pt1 MPW2025 레이아웃에 기록된 판), 킷의 `qflow-1.4.100_etri050.tar.gz`. 킷 qflow 압축본은 qflow 1.4.100(커밋 b0f76bf)에 `tech/etri050` 추가와 파이썬 정규식 수정만 더한 것이다.
- 핀 변: 스캔 입출력은 아래(남쪽 패드), 어레이·RO 선택은 위, CBCM 선택은 오른쪽(칩 배치도 기준).
- 기술 디렉터리의 링크는 킷 `Tools/qflow-1.4.100_etri050_build.sh`와 같다. 그래서 qflow가 `layout/.magicrc`로 복사하는 파일이 킷 템플릿의 `layout/.magicrc`(= `digital_ETRI/khu_etri050.magicrc`)와 같다.
- 상태: 아직 실행 전이다. qflow 디렉터리 탐색 규칙(`checkdirs.sh`: `QFLOW_TECH_DIR` → 프로젝트 `tech/<이름>`)과 킷 Makefile 순서를 따라 썼고, 도구를 설치한 뒤 첫 실행 결과(셀 수, 블록 크기, 배선 실패 수, DRC·LVS)로 이 절을 갱신한다. 비교 기준으로 킷 FIR_PE(MPW240925002) 최종 코어의 로그는 LVS "Circuits match uniquely"(소자 847·넷 865 일치), 스택 비아 "No stacked Contact and/or Via found.", DRC는 "has 24 error tiles"와 "Total DRC errors found: 0"이 함께 찍히고 사유는 "This layer can't abut or partially overlap between subcells" 하나다.
