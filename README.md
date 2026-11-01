# 마이칩(ETRI 0.5 µm)·Tiny Tapeout 웹 EDA 데스크톱

브라우저 탭 하나로 Magic, KLayout, Xschem, ngspice, Netgen을 쓰는 설정이다. GitHub Codespaces가 IIC-OSIC-TOOLS 컨테이너를 띄우고, 컨테이너 안의 VNC 데스크톱을 noVNC로 브라우저에 보여 준다. ETRI 0.5 µm 오픈소스 디자인 킷은 codespace를 처음 만들 때 자동으로 받는다.

```
.devcontainer/devcontainer.json   이미지, 포트(6080), 시작 명령
.devcontainer/start-desktop.sh    Xvnc + XFCE + noVNC 시작 (다시 실행해도 안전)
scripts/setup-etri050.sh          ETRI 킷 받기(sparse) + 연결
scripts/etri050-env.sh            magic-etri, etri-drc, etri-lvs 등 단축 명령
designs/etri050/                  ETRI 작업 폴더 (xschemrc, 예제 회로도·시뮬레이션)
designs/tinytapeout/              Tiny Tapeout 작업 폴더
```

## 1. 처음 한 번

1. 이 폴더 내용을 GitHub 새 저장소(비공개 가능)에 올린다.
2. 저장소 페이지 → **Code → Codespaces → ⋯ → New with options** → Machine type을 고른다. 2-core부터 시작하고, 느리면 4-core로 바꾼다.
3. 첫 생성은 이미지(압축 약 4 GB)를 받느라 오래 걸린다. 끝나면 `scripts/setup-etri050.sh`가 ETRI 킷(약 50 MB)을 `.pdk/` 아래에 받는다.
4. 데스크톱 탭이 자동으로 안 열리면 VS Code 아래 **Ports** 탭 → "EDA Desktop (noVNC)"(6080)의 지구본 아이콘을 누른다. 비밀번호는 `abc123`이다. 주소 끝에 `/?password=abc123`을 붙이면 바로 접속된다.

포트는 기본이 비공개라 본인 GitHub 계정으로만 열린다. Public으로 바꾸지 않는다.

### 설치 확인

```bash
bash scripts/smoke-test.sh
```

NMOS 하나(W/L = 3/0.6 µm)를 코드로 그려 흐름 전체를 돌린다. 도구·킷 파일, ngspice 예제(Vt), Xschem 넷리스트, Magic DRC, GDS 층 번호(ACT 11, POLY1 12, CONT 31), KLayout DRC, LVS(소자·W/L·핀), noVNC 포트를 검사하고 끝에 `SMOKE TEST: N passed, …`를 출력한다. 결과 파일은 `/tmp/etri050-smoke`에 남는다.

## 2. ETRI 0.5 µm 작업

새 터미널(데스크톱 터미널이나 VS Code 터미널)에서 쓰는 명령이다. VS Code 터미널에서 실행한 GUI도 noVNC 데스크톱에 뜬다(`DISPLAY=:1`).

| 명령 | 하는 일 |
|---|---|
| `magic-etri [cell]` | ETRI 기술 파일로 Magic 실행 |
| `klayout-etri [file.gds]` | ETRI 레이어 색으로 KLayout 실행 |
| `xschem-etri [file.sch]` | ETRI용 설정(`designs/etri050/xschemrc`)으로 Xschem 실행 |
| `etri-drc <cell>` | 현재 폴더 `<cell>.mag`의 Magic DRC |
| `etri-gds <cell>` | `<cell>.mag` → `<cell>.gds` (ETRI 층 번호로 출력) |
| `etri-gds-read <file.gds>` | KLayout 등에서 만든 ETRI GDS를 Magic 셀(.mag)로 가져오기 |
| `etri-drc-klayout <file.gds>` | KLayout DRC (킷의 NSPL 규칙 v1.1 덱) |
| `etri-lvs <cell> <schematic.spice> [subckt]` | Magic 추출 → Netgen LVS |
| `etri-check <cell> [schematic.spice]` | Magic DRC, GDS 출력, KLayout DRC, LVS를 한 번에 하고 한 줄로 요약 |

### 예제

- **시뮬레이션:** `cd designs/etri050/sim && ngspice -b nmos_idvg.spice`
  27 °C에서 Vt(20/20 µm) 0.665 V, Vt(20/0.5 µm) 0.742 V, Idsat(20/0.5 µm) 556 µA/µm가 나온다. PDK 전기적 목표(0.70 ± 0.1 V, 550 ± 50 µA/µm) 안이다. 125 °C 값도 함께 출력한다.
- **회로도:** `cd designs/etri050 && xschem-etri sch/nmos_tb.sch` → Netlist → Simulate.
  모델은 코드 블록에 `format="tcleval( @value )"`, `value=".include $::ETRI050_MODEL"`로 넣는다.
- **패드 프레임:** `.pdk/ETRI050_DesignKit/pads_ETRI/GDS/MPW_PAD_28pin.gds` (1.9 × 1.9 mm, 패드 28개)

### TEG 트랜지스터 생성 (코드로 그리기)

```bash
python3 designs/etri050/gen/etri050_mos.py                 # 표(devices_v0.csv) 전체 + 배열, 검사까지
python3 designs/etri050/gen/etri050_mos.py nmos:18:0.6 --check   # 셀 하나 (종류:W:L, µm)
klayout-etri designs/etri050/teg/build/teg_v0.gds          # noVNC 데스크톱에서 보기
```

- Python이 λ 격자(0.3 µm) 위에서 좌표를 계산해 Magic 명령을 만들고, Magic이 배치 모드로 그린다. 컨택 컷·임플란트·웰은 Magic의 ETRI 출력 스타일이 만든다.
- 셀은 4단자 단일 핑거(포트 순서 D G S B)이고, LVS용 회로도 넷리스트(`build/sch/<cell>.spice`)를 함께 만든다.
- 제약: W ≥ 1.8 µm, L ≥ 0.6 µm, 둘 다 0.3 µm의 배수. Magic 규칙의 최소 poly 폭이 2λ = 0.6 µm라서 공식 최소 L 0.5 µm는 이 흐름으로 그리지 않는다. 20 µm도 격자에 맞지 않아 기준 폭은 18 µm로 둔다.
- 표의 W/L은 흐름 확인용 초안이다. 최종 목록은 식별가능성 분석으로 정한다.
- 결과는 `designs/etri050/teg/build/`에 생기고 git에는 올리지 않는다(코드가 원본).

### 통합 TEG 칩 v0

```bash
python3 designs/etri050/gen/etri050_teg_chip.py                  # 블록 → 배선 → DRC·LVS → 칩 GDS
klayout-etri designs/etri050/teg/build/chip/teg_chip_v0.gds      # noVNC 데스크톱에서 보기
```

- 구성: 킷의 28핀 맨 패드 프레임(`pads_ETRI/GDS/MPW_PAD_28pin.gds`, 1.9 × 1.9 mm)에 블록 세 개를 넣는다.
  - NMOS 행렬 8개: 게이트·소스·기판은 공유하고, 드레인은 소자마다 패드 하나
  - PMOS 행렬 6개: 게이트·소스·N-well 공유, 드레인은 따로
  - MOS 커패시터: NMOS 90 × 90 µm(약 25 pF), 소스·드레인·바디는 기판에 묶음(C–V용)
- 패드 28개 중 21개를 쓰고, 7개는 다음 판(PNP, Kelvin 저항, 여분)을 위해 비운다. 패드 표(번호, 넷, 배선 길이)는 `build/chip/teg_chip_v0_pins.md`에 생긴다.
- 소자 목록은 `designs/etri050/teg/teg_chip_v0.json`에서 바꾼다. 패드 배치 때문에 NMOS는 8개, PMOS는 6개로 고정이다.
- 칩 배선은 전부 metal3이고, 서로 교차하지 않게 겹겹이 배치한다. 드레인 12 µm, 공유 소스 30 µm, 기판·N-well 20 µm, 게이트 4.2 µm 폭이다.
- 검사: 블록과 코어의 Magic DRC, 코어와 칩 전체의 KLayout DRC, 코어 LVS(패드 넷을 포트로 비교), 패드 점검(쓰는 패드에는 자기 넷만, 빈 패드에는 아무것도 닿지 않음).
- 칩 GDS는 ETRI 패드 프레임 GDS를 그대로 두고, Magic이 쓴 코어 GDS를 합친 것이다.
- 알아둘 점
  - ESD 보호가 없다. 게이트가 맨 패드에 바로 붙으니 칩을 다룰 때 정전기를 조심한다.
  - 패키지 핀 번호는 ETRI 본딩도를 따른다. 보드를 만들기 전에 확인한다.
  - 공유 소스와 드레인의 배선 저항이 측정에 들어간다. 패드 표의 square 수에 PDK의 metal 시트 저항을 곱해 보정한다.
  - 안테나 규칙은 오픈소스 덱에 없다. 공식 Calibre 덱이나 운영 측 검증으로 확인한다.

### 온칩 특성화 IC 블록 (진행 중)

통합 TEG를 스캔 제어 + Kelvin 어레이 + CBCM + RO 뱅크 + 직결 기준 소자로 묶는 칩의 블록 검증 자료다.

- `designs/etri050/ctrl/`: 제어 블록 `teg_ctrl`(20비트 스캔, 섀도 레지스터, 블록 디코더, RO 선택·÷256). `make sim synth gatesim`으로 RTL·합성·게이트 수준 검사, `make flow`로 qflow 배치·배선(킷 FIR_PE 흐름).
- `designs/etri050/sim/blocks/`: 어레이 경로, 스위치 TG, CBCM, RO 뱅크, 스캔·분주, PNP 온도계, L-split의 ngspice 검사. `python3 run_all.py`가 설계 계획의 수치와 비교한다. 공식 PDK 모델은 킷 문서 폴더의 압축본에서 꺼내므로 `ETRI050_WITH_DOCS=1 bash scripts/setup-etri050.sh`가 한 번 필요하다.

### 마이칩 제출 조건 (ETRI 소개 자료, 2026-06 기준)

- 칩 1.9 × 1.9 mm, 팀당 설계 면적 1.5 × 1.5 mm (GPIO를 쓰면 1.0 × 1.0 mm). 패키지를 하지 않으면 패드를 자유롭게 배치할 수 있다.
- 설계를 끝낸 뒤 신청서와 설계 DB를 모아팹에 팀 단위로 접수한다. 칩은 DB 제출 약 5개월 뒤에 받는다.
- 팀당 패키지 칩 20개(28-pin SOP)와 bare die 30개를 받는다. 측정할 때는 패키지 윗면을 검은 테이프 등으로 가려 빛을 막는다.
- 공식 검증 덱은 Calibre·Assura용이다. 이 환경의 Magic·KLayout 검사는 오픈소스 변환본이니, 제출 전 검증 절차는 공고문으로 확인한다.

### 주의

- 킷의 `sch/fet_models.sym`에는 MOSIS AMI C5 모델이 들어 있다. ETRI 결과가 아니니, 반드시 `spice/05cmos_model_240201.lib`(소자 이름 nfet/pfet)를 쓴다.
- 공식 PDK(260820)의 모델 파일 `05cmos_model_260210`은 소자 이름이 nmos4/pmos4다. Magic 추출 이름(nfet/pfet)과 섞으면 LVS가 어긋난다.
- Magic에서 `gds write`를 직접 칠 때는 먼저 `cif ostyle lambda=0.30(ETRI)`를 지정한다. 기본 스타일은 MOSIS 층 번호(41, 43, …)로 써서 ETRI 제출용이 아니다. `etri-gds`는 이걸 자동으로 한다. 패드 프레임처럼 이미 ETRI 층인 GDS를 그대로 합칠 때는 킷의 `scripts/generate_chip.sh`처럼 `lambda=0.30(ETRI-G)` 스타일을 쓴다.
- 온도 특성: ETRI 소개 자료(2026-06)는 모델에 25~125 °C 온도 파라미터가 있다고 밝히지만, 모델 파일 머리말에는 아직 미포함이라고 적혀 있다. 125 °C 결과는 실측으로 확인하기 전까지 모델 값으로만 본다.
- `etri-lvs`는 추출 결과를 `<cell>.spice`로 저장한다. 회로도 넷리스트는 다른 폴더(예: `netlist/`)에 두고, Xschem에서는 top level을 `.subckt`로 감싼 LVS용 넷리스트를 뽑는다.
- LVS에서 핀 이름까지 비교하려면 레이아웃의 라벨을 포트로 만든다. Magic 명령창에서 셀 전체를 box로 덮고 `port makeall`을 실행한 뒤 저장한다. 포트가 없으면 `etri-lvs`는 소자와 연결만 비교하고 그 사실을 알려 준다. 결과 줄은 `ETRI-LVS <cell>: MATCH`이고, W/L이 다르면 `MATCH but property errors`로 나온다.
- 오픈소스 DRC 덱은 공식 Calibre 규칙을 옮긴 것이다. 최종 제출 전 검증 절차는 운영 측 안내를 따른다.
- KLayout 덱(`etri_05um_generated_final.drc`)에는 poly 엔드캡, 게이트 밖 ACT 길이, ACT 컨택–게이트 간격, NSD/PSD의 ACT 감쌈 같은 규칙이 없다. 그래서 Magic DRC(λ 규칙, 더 보수적)와 함께 돌린다. `etri-check`가 둘 다 한다.
- ngspice-47(이 이미지)은 `echo` 출력에서 `=` 앞뒤 공백을 지운다. 출력을 파싱할 때 공백이 있다고 가정하지 않는다.
- 이미지의 기본 PDK는 IHP SG13G2라서 그냥 `klayout`을 열면 SG13G2 메뉴와 technology가 붙는다. ETRI 레이아웃은 `klayout-etri`로 연다(IHP 설정을 빼고 ETRI 레이어 색, 전체 계층 표시로 연다).
- 이 이미지의 qflow는 변환 도구(vlog2Verilog 등)만 들어 있고, 킷의 디지털 배치배선에 필요한 qflow·graywolf·qrouter·tcsh는 없다(2026-11-01 확인). sudo는 비밀번호를 요구하므로 `bash scripts/install-qflow-etri050.sh`로 루트 없이 `~/.local/etri050-tools`에 설치한다. 새 터미널부터 PATH에 들어가고, 배치배선은 `designs/etri050/ctrl/run_flow.sh`(설명은 그 폴더 README)가 맡는다.

## 3. Tiny Tapeout

1. 현재 터미널의 PDK 전환: `sak-pdk sky130A` 또는 `sak-pdk ihp-sg13g2`
2. 아날로그 템플릿을 `designs/tinytapeout/` 아래에 받는다.
   `git clone https://github.com/TinyTapeout/ttsky-analog-template` (IHP는 `ttihp-analog-template`)
3. 그 폴더에서 `magic`을 실행하면 PDK의 magicrc가 자동으로 적용된다. DRC는 `sak-drc.sh -m <cell>`, LVS는 `sak-lvs.sh -s <schematic> -l <layout> -c <cell>`
4. 템플릿 README가 요구하는 PDK·Magic 버전을 먼저 확인한다. Tiny Tapeout은 Magic 버전이 PDK와 맞아야 한다고 안내한다.

## 4. 비용과 한도 (중요)

- 개인 무료 계정은 월 120 코어시간(2-core로 약 60시간), 저장 15 GB-month다. GitHub Pro(학생 팩 포함)는 180 코어시간, 20 GB-month다.
- 커스텀 이미지는 저장 용량에 포함된다. 이 이미지는 압축 4 GB이고 풀면 훨씬 커서(공식 안내: 여유 공간 20 GB 이상), codespace를 한 달 내내 두면 무료 저장 한도를 넘을 수 있다.
- 작업이 끝나면 Stop하고, 며칠 안 쓸 때는 커밋·푸시한 뒤 Delete한다. 다시 만들 때는 이미지를 다시 받는 시간이 든다.
- 오래 쓸 거라면 같은 `.devcontainer`를 내 PC의 Docker와 VS Code Dev Containers에서 그대로 열 수 있다. 이 경우 한도가 없다.

## 5. 문제 해결

- **데스크톱이 안 뜸:** 터미널에서 `bash .devcontainer/start-desktop.sh`를 실행하고 `/tmp/iic-desktop.log`를 본다.
- **화면 크기:** noVNC가 브라우저 창 크기에 맞춰 바뀐다. 고정하려면 왼쪽 막대 설정의 Scaling Mode를 바꾼다.
- **복사·붙여넣기:** noVNC 왼쪽 막대의 Clipboard를 쓴다.
- **도구 버전 고정:** `devcontainer.json`의 `latest`를 날짜 태그로 바꾼다.

## 출처

- [IIC-OSIC-TOOLS](https://github.com/iic-jku/IIC-OSIC-TOOLS)
- [ETRI 0.5um CMOS MPW 오픈소스 디자인 킷](https://github.com/GoodKook/ETRI-0.5um-CMOS-MPW-Std-Cell-DK)
- [Tiny Tapeout analog specs](https://www.tinytapeout.com/specs/analog)
- [GitHub Codespaces 사용량 측정 방식](https://docs.github.com/en/billing/concepts/product-billing/github-codespaces)
