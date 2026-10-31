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

## 2. ETRI 0.5 µm 작업

새 터미널(데스크톱 터미널이나 VS Code 터미널)에서 쓰는 명령이다. VS Code 터미널에서 실행한 GUI도 noVNC 데스크톱에 뜬다(`DISPLAY=:1`).

| 명령 | 하는 일 |
|---|---|
| `magic-etri [cell]` | ETRI 기술 파일로 Magic 실행 |
| `klayout-etri [file.gds]` | ETRI 레이어 색으로 KLayout 실행 |
| `xschem-etri [file.sch]` | ETRI용 설정(`designs/etri050/xschemrc`)으로 Xschem 실행 |
| `etri-drc <cell>` | 현재 폴더 `<cell>.mag`의 Magic DRC |
| `etri-gds <cell>` | `<cell>.mag` → `<cell>.gds` |
| `etri-drc-klayout <file.gds>` | KLayout DRC (킷의 NSPL 규칙 v1.1 덱) |
| `etri-lvs <cell> <schematic.spice> [subckt]` | Magic 추출 → Netgen LVS |

### 예제

- **시뮬레이션:** `cd designs/etri050/sim && ngspice -b nmos_idvg.spice`
  27 °C에서 Vt(20/20 µm) 0.665 V, Vt(20/0.5 µm) 0.742 V, Idsat(20/0.5 µm) 556 µA/µm가 나온다. PDK 전기적 목표(0.70 ± 0.1 V, 550 ± 50 µA/µm) 안이다. 125 °C 값도 함께 출력한다.
- **회로도:** `cd designs/etri050 && xschem-etri sch/nmos_tb.sch` → Netlist → Simulate.
  모델은 코드 블록에 `format="tcleval( @value )"`, `value=".include $::ETRI050_MODEL"`로 넣는다.
- **패드 프레임:** `.pdk/ETRI050_DesignKit/pads_ETRI/GDS/MPW_PAD_28pin.gds` (1.9 × 1.9 mm, 패드 28개)

### 주의

- 킷의 `sch/fet_models.sym`에는 MOSIS AMI C5 모델이 들어 있다. ETRI 결과가 아니니, 반드시 `spice/05cmos_model_240201.lib`(소자 이름 nfet/pfet)를 쓴다.
- 공식 PDK(260820)의 모델 파일 `05cmos_model_260210`은 소자 이름이 nmos4/pmos4다. Magic 추출 이름(nfet/pfet)과 섞으면 LVS가 어긋난다.
- 모델 머리말에 온도 파라미터가 포함되지 않았다고 적혀 있다. 125 °C 결과는 모델의 추정일 뿐이다.
- `etri-lvs`는 추출 결과를 `<cell>.spice`로 저장한다. 회로도 넷리스트는 다른 폴더(예: `netlist/`)에 두고, Xschem에서는 top level을 `.subckt`로 감싼 LVS용 넷리스트를 뽑는다.
- 오픈소스 DRC 덱은 공식 Calibre 규칙을 옮긴 것이다. 최종 제출 전 검증 절차는 운영 측 안내를 따른다.
- 이 이미지의 qflow는 변환 도구 용도라, 킷의 ETRI용 디지털 자동 배치배선 흐름은 이 설정에서 다루지 않는다. 이 설정은 풀커스텀 기준이다.

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
