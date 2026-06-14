# RWA 公司行动监控看板

## 文件结构
```
├── index.html                        # 前端看板页面
├── fetch_data.py                     # 数据拉取脚本（GitHub Actions 运行）
├── data.json                         # 自动生成，不需要手动编辑
└── .github/workflows/update.yml     # 定时任务配置
```

## 部署步骤

### 第一步：上传文件到 GitHub
1. 新建 repo（建议命名 `rwa-ca-monitor`），设为 **Public**
2. 上传所有文件，注意 `.github/workflows/update.yml` 路径要保持不变

### 第二步：配置 API Key（存在 GitHub Secrets，不会暴露）
1. 进入 repo → Settings → Secrets and variables → Actions
2. 点「New repository secret」，添加两个：
   - Name: `POLYGON_KEY`  Value: 你的 Massive/Polygon API Key
   - Name: `FMP_KEY`      Value: 你的 FMP API Key

### 第三步：手动触发第一次运行
1. 进入 repo → Actions → 「每日公司行动数据更新」
2. 点「Run workflow」手动跑一次，生成 `data.json`

### 第四步：开启 GitHub Pages
1. Settings → Pages → Branch: main → Save
2. 访问 `https://你的用户名.github.io/rwa-ca-monitor`

## 运行时间
- 北京时间 **08:30** 自动拉取（美股前一天结算后）
- 北京时间 **21:30** 自动拉取（捕捉当天宣告的特别分红）

## 注意事项
- FMP 免费层限制 250次/天，当前24个标的每次约48次调用，每天两次共96次，在限额内
- SPCX、CRWV、CRCL 为新上市标的，API可能数据不完整，看板会自动标注并提供人工核查链接
- 数据冲突（两源不一致）时会显示红色警报，**禁止直接操作系数，必须人工核查**
