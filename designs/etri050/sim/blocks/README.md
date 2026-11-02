# 블록 검증 시뮬레이션 (ngspice)

온칩 특성화 IC의 아날로그·혼성 블록이 공식 PDK 모델로 동작하는지 확인하는 스크립트다. 결과 숫자는 칩 설계 계획의 근거로 쓰였고, `run_all.py`가 그 값과 다시 비교한다.

## 준비

공식 PDK 모델(05cmos_model_260210.lib, 05cmos_mosfet_corner.lib)은 킷의 문서 폴더 압축본에서 꺼내 `build/`에만 둔다(저장소에는 넣지 않는다). 문서 폴더가 없으면 한 번 받는다.

```bash
ETRI050_WITH_DOCS=1 bash scripts/setup-etri050.sh        # docs/ETRI_0p5um_NSPL_260820 추가(약 110 MB)
# 또는 모델 두 파일이 있는 폴더를 지정: export ETRI050_PDK_MODELS=/path/to/Model_Parameter
```

킷 표준셀 넷리스트(khu_etri050_stdcells.spice)는 PDK 소자 이름에 맞춰 nfet/pfet → nmos4/pmos4로 바꿔 쓴다.

## 실행

```bash
cd designs/etri050/sim/blocks
python3 run_all.py              # 전부
python3 run_all.py tg pnp       # 일부만
python3 run_all.py post         # 레이아웃 뒤 어레이(designs/etri050/array/build/kelvin_r.json이 있을 때 기본 실행에도 들어감)
python3 run_all.py chip         # 칩 전체 트랜지스터 수준(designs/etri050/chip/build/pdkv_Top.gds가 있을 때 기본 실행에도 들어감)
```

실행 시간(Codespace 4코어, ngspice-47, 2026-11-01): 전체 약 10분 — RO 384 s(과도 해석 38회), CBCM 128 s(23회), scan 58 s(스캔 6회 + 분주 9회), 나머지는 각각 10 s 이내. 이때 결과는 `BLOCK CHECKS: 23 ok, 0 to check`였다(킷 db09a3d, 111dc09와 문서 PDF 두 개만 다름). CBCM 블록 두 단계가 더해져 cbcm_block 228 s(54회), cbcm_post 373 s(97회)가 늘었고, 두 단계의 15개는 모두 ok였다(같은 날, 같은 환경). 로컬 ngspice-42(2코어)에서도 같은 값이 나온다. 칩 전체 단계 `chip`(`chip_post.py`)은 이름을 줄 때만 돈다(`python3 run_all.py chip`): 로컬 ngspice-42 2코어에서 42분(2026-11-02, 넷리스트 추출 1분 반 뒤 과도 해석 6개를 두 개씩: 스캔 세 코너 각 약 10분, RO 0 28분, CBCM 24분, RO 3 5분)이고 결과는 `BLOCK CHECKS: 37 ok, 0 to check`였다.

끝에 `BLOCK CHECKS: N ok, M to check`가 나온다. CHECK는 계획 값과 허용 범위 밖이라는 뜻이고(ngspice 판이나 모델 파일이 다를 때 등), 원인을 확인할 대상이다.

| 스크립트 | 확인 내용 | 계획에 쓴 값 |
|---|---|---|
| tg_ron.py | 어레이 스위치 TG의 0.05–4.95 V 최대 Ron | N100/P250: 45 Ω(TT 27 °C), 62 Ω(SS 125 °C) |
| array_path.py | 8×8 NMOS 어레이 경로(PANA 다이오드, 미선택 행·열, Kelvin SMU) 대 이상 소자 | 문턱 이상 전류 오차 ≤ 0.04%, 27 °C ΔVt ≤ 0.012 mV, 125 °C 누설 1.2–5.5 nA, open 채널 차감 후 ΔVt ≤ 0.06 mV |
| array_kelvin.py | 드레인 sense를 열 끝에서 받을 때와 셀마다 받을 때(행 선택 TG) 비교, 먼 행·MET2 열 선로 | 셀 sense: R_tot 오차 ≤ 0.01%. 열 끝 sense: +1.1%(선로 10 µm)·+1.8%(6 µm) |
| array_post.py | 레이아웃 뒤: array_path 하네스에 셀 sense TG, 그린 스위치 크기, 그린 어레이에서 뽑은 Kelvin 루프 안 저항(`designs/etri050/array/kelvin_r.py`) | W/L 9/0.6 R_tot +0.16 %(typ)·+0.24 %(최대), typ 표를 빼면 ≤ 0.08 %, 다른 셀 ≤ 0.03 %. ΔVt 27 °C ≤ 0.004 mV, 125 °C open 뺀 뒤 ≤ 0.047 mV |
| cbcm.py | CBCM 정확도·주파수·PADR 영향·125 °C·C–V | 300 fF +1.2%, 1 pF +0.3%, PADR 영향 ≤ 0.3%p |
| cbcm_block.py | 그린 CBCM 블록의 회로 넷리스트(`designs/etri050/gen/etri050_cbcm.py`): 비중첩 생성기, 셀마다 PMOS 게이트 NAND2X1, 공통 NMOS 게이트, 10개 셀과 구조 모델(PIP·N+는 PDK 모델, 금속은 규칙 문서 값). 5코너·125 °C·VDD 4.5/5.5 V·0.2/1/5 MHz | 300 fF 셀 +1.49 %, 게이트 +0.2 %, 빈 셀 0.00 fF, 비중첩 ≥ 0.30 ns(FF, 4.5 V), 미선택 셀 영향 0.002 %, PADR +0.24 %p, C–V(1.5–5 V) ≤ 0.51 % |
| cbcm_post.py | 레이아웃 뒤 CBCM: cbcm_block의 넷리스트에 그린 블록의 배선 용량(`designs/etri050/cbcm/cbcm_c.py`, 규칙 문서 용량표)과 그린 기하의 구조 모델(PIP pipcap_i, N+ ndiode, 게이트 nmos4)을 넣는다. N+ 셀은 ndiode와 nmos4 소스·드레인 접합 값을 함께 낸다 | 빈 셀 0.00 fF, 셀 2 +4.50 fF(+1.47 %, 코너·VDD·클록에 따라 +1.34–1.68 %), 게이트 +0.2 %, 비중첩 ≥ 0.47 ns, PADR +0.25 %p, C–V(셀 6–9, 1.5–5 V) ≤ 0.96 % |
| ro_bank.py | 31단 RO 6종 × 5코너(27 °C) + TT 125 °C, INV RO의 VDD 4.5–5.5 V | INV 123.1, NAND 93.8, NOR 66.8, FO4 52.8, 배선 65.0, 저항 69.1 MHz(TT 27 °C) |
| ro_post.py | 그린 RO 뱅크(`designs/etri050/gen/etri050_ro.py`)의 넷리스트: 탭 INVX1 → INVX4 포함. 계획 부하(마디마다 5 fF, 배선 RO 43.5 fF)로 한 번, 그린 GDS의 배선 용량(규칙 문서 용량표, `cbcm_c.py`의 추출기)으로 5코너·125 °C | 계획 부하: INV 121.8, NAND 93.1, NOR 66.4, 배선 64.6 MHz(ro_bank보다 탭만큼 0.4–1.1 % 느림). 그린 배선: 99.2, 83.2, 60.6, 55.9 MHz(마디 배선 13–25 fF, 계획 가정 5 fF) |
| scan_divider.py | 8비트 스캔 + 섀도 + 3→8 디코더(3 PVT × 1·10 MHz), 분주기 ÷16(100–200 MHz) | 모두 정상 |
| pnp_thermo.py | pnp10 온도계(PADR 경유) 3전류법 대 2전류법 | 3전류법 오차 ≤ +0.16 K(27–125 °C), 2전류법 −4.9 K(125 °C) |
| lsplit.py | W 9 µm 포화 전류, Terada–Muta(L 0.6·1.2·3·9 µm) | 4.56 mA, R_sd 121 Ω(27 °C)·135 Ω(125 °C) |
| chip_post.py | 칩 전체(패드 링 안)를 트랜지스터 수준으로: `designs/etri050/chip/chip_lvs.py`가 칩 GDS에서 뽑아 기준과 일치시킨 넷리스트(소자만). 스캔 5프레임(모드 01·01·00·10·11)에서 SLE 뒤와 다음 프레임 중간의 선택·enable 선 55개, OUT 읽기 80비트(TT 27 °C 5 V·SS 125 °C 4.5 V·FF 27 °C 5.5 V). 어레이 I(ADF) 대 측정이 가정하는 소자(게이트 AG, 드레인 ADS 전압, 소스 SRC), 선택 행 게이트 − AG, I(AG), mode 00. CBCM 셀 1(PIP)·셀 0과 CBCM_CLK 게이트, enable. RO 0 ÷256과 주파수, RO 3(없음) 정지 | 세 코너 모두 선 틀림 0, 읽기 틀림 0/80. NMOS 2행 0열 1.692 mA 오차 0.0000 %, PMOS 9행 1열 0.320 mA −0.002 %(SS −0.007 %), 게이트 − AG 0 mV, I(AG) ≤ 57 pA, mode 00 ≤ 67 pA(gmin). CBCM 셀 1 465.55 fF = 블록 넷리스트 +0.10 fF(그린 판 460.80 fF), 빈 셀 0.004 fF, CBCM_CLK mode 10에서 창마다 6번·mode 01에서 22 µV. RO 0 133.9 MHz(같은 reltol의 블록 넷리스트 134.2 MHz, −0.2 %), OUT 반주기 × f = 128.00, RO_EN0만 켜짐. RO 3: enable 0, 탭·RO 멀티플렉서·OUT 정지 |

PANA ESD 다이오드는 킷 GPIO GDS(ETRI_NSPL_GPIO_250610)에서 읽은 크기(극성마다 10 × 10 µm 12개, 면적 1200 µm²·둘레 480 µm)로 넣었다. 배선 저항·기생 용량은 추정값이므로 레이아웃 추출 뒤 다시 돌린다. 어레이는 `array_post.py`로 다시 돌렸다: 계획 하네스의 소스 판은 sense 탭에 전류가 흐르지 않아 이상적이었고, 그린 어레이의 소스 비아·판(셀마다 0.42–0.68 Ω, typ)이 W/L 9/0.6 셀에서 +0.16 %로 드러난다(`designs/etri050/array/README.md`).

## 칩 전체 (`chip_post.py`)

레이아웃 뒤 블록 모의와 달리 패드 링 안 전체를 한 번에 돌린다. `designs/etri050/chip/chip_lvs.py`가 칩 GDS에서 뽑아 기준과 일치시킨 넷리스트(MOS 3071개의 W·L·접합 면적·둘레, poly2 저항 31, PIP 1, pnp10 2; 넷 이름은 일치 뒤 기준 이름)를 그대로 쓰므로, 고정한 제어 매크로(셀 255개)까지 그린 트랜지스터 그대로 레지스터 맵대로 도는지를 본다. 킷 표준셀 넷리스트는 킷 셀 레이아웃의 Magic 추출본이라, LVS는 그린 셀이 그 넷리스트와 같다는 것만 보이고 셀이 맞게 동작하는지는 이 모의(와 블록 단계의 `scan_divider.py`)가 본다. 패드는 패드 셀 코어 포트의 전원이고(SCK·SDI·SLE·CCK는 PIC 출력 자리, OUT은 POB4 입력 대신 0.1 pF) 배선 기생은 넣지 않는다. 어레이의 비교 기준은 측정이 가정하는 소자 하나(게이트 AG, 드레인은 ADS로 읽은 전압, 소스 SRC)라서, 칩 경로(선택 스위치, 선택 안 된 셀, sense 선)가 더하는 차이와 게이트가 AG에 닿지 않는 잘못이 함께 드러난다.

- 수치 설정: DC 해를 구하지 않고(uic, 래치와 링이 많은 칩에는 쓸 만한 해가 없음) 전원과 패드 전압을 20 ns 동안 함께 올리며, gear 적분과 abstol 1 pA를 쓴다. 스캔은 reltol 1e-3이다. 보는 값이 모두 안정된 값이라 같은 회로·자극에서 1e-4와 같은 값을 3분의 1 시간에 낸다. RO도 1e-3이고 블록 넷리스트를 같은 reltol로 돌려 비교한다(reltol만으로 블록의 RO 0이 1e-4에서 135.7, 1e-3에서 134.2 MHz). CBCM은 `cbcm_block.py`처럼 1e-5다. 주기당 전하가 큰 두 전하의 작은 차이라, 그린 판 대비 셀 1을 1e-3에서 −5.4 fF, 1e-4에서 +2.84 fF로 읽었고(100 Ω을 넣기 전 덱, 그때 1e-5는 "timestep too small"로 멈춤) 1e-5에서 +4.75 fF로 블록 넷리스트의 +4.65 fF와 0.10 fF 안이다.
- 직류가 흐르지 않는 패드(게이트·접합만 충전)는 100 Ω을 거쳐 구동한다. 이상 전원의 분기 전류가 반올림뿐이라, 클록 모서리에서 시간 간격이 작아지면 그 전류가 수렴하지 못해 모의가 멈췄다("timestep too small … vlg#branch": 같은 회로가 소자 순서만 바뀌어 0.30 µs·2.85 µs에서). 직류가 흐르는 패드(VDD, 어레이 프레임의 ADF·SRC)는 이상 전원 그대로다. 이렇게 고친 뒤 소자를 거꾸로 써도(같은 회로) 스캔 세 코너와 CBCM이 끝까지 돌고 값도 같다(선·읽기 틀림 0, 어레이 오차 같은 자리까지, CBCM 셀 1 − 블록 넷리스트 +0.09 fF).
- 소자는 늘 같은 순서(종류·넷 이름순, MOS 드레인은 낮은 넷 이름)로 써서 같은 회로면 같은 덱이 나온다. SDI는 SCK가 떨어진 뒤 25 ns에 바꿔(받는 상승 모서리 25 ns 전, 앞 모서리 75 ns 뒤) 소스의 꺾임이 클록 모서리와 겹치지 않는다.
- pA 단위 값(mode 00의 I(ADF), I(AG), CBCM 휴지 전하)은 시뮬레이터 gmin(1e-12 S)에서 나온 값이고 실제 누설이 아니다. 이 검사들은 아무것도 선택되지 않았음을 본다.
- RO 0을 돌릴 때 RO_IN2는 배선 용량이 없어 RO 멀티플렉서 게이트를 거쳐 0.14 V 흔들린다. 정지 판정 한계는 그래서 1 V다(도는 링의 탭은 0–5 V).
- L-split·히터·PNP는 넣지 않았다. 단자가 모두 패드라 LVS로 소자가 맞으면 트랜지스터 수준 모의가 볼 것이 없다(`lsplit.py`, `pnp_thermo.py`가 그 검사).
- 한계: 제어 블록의 배선 기생은 어디서도 모의하지 않았다(qflow STA는 서명 항목이 아님). 그래서 세 코너의 스캔은 동작을 보이고 타이밍 여유는 보이지 않는다. CBCM과 RO는 TT 27 °C만 돌린다(코너·온도는 `cbcm_post.py`·`ro_post.py`).
