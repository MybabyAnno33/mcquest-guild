# MCP API 实测笔记（McQuest Guild）

> 本文件只记录本项目已实际取得的验证结果（2026-10-22 ~ 2026-10-23，麦当劳中国 MCP，深圳测试）。
> 未标注"已实测"的内容一律视为未验证，不得在任务中当作事实使用。

## 1. query-nearby-stores（已实测 ✅）

- 必填：`searchType`(integer, 枚举 1/2, 默认 1)、`beType`(integer, 枚举 1/5)。
- `searchType=2`（按位置搜索）时，工具描述要求 `city` 与 `keyword` 必填；`searchType=1` 为搜收藏餐厅。
- `beType=1` 到店自提；`beType=5` 得来速（返回 `beCode`，后续调用必传）。
- **自提（beType=1）结果不包含 `beCode` 字段**。
- 实测参数：`{searchType:2, city:"深圳市", keyword:"深圳", beType:1}` → 成功返回 5 家深圳北站门店。
- 返回字段：`storeCode`、`storeName`、`address`、`distance`、`businessStatus`、`businessStartTime`、`businessEndTime`、`longitude`/`latitude`、`reservation`、`reservationTimeOptions[].{date, today, reservationOptionText}`。
- **未明确**：`keyword` 匹配粒度；返回条数上限（无 limit 参数）。

### 关键词兜底行为（2026-10-25 实测观察）

- 实测参数：`{searchType:2, city:"深圳市", keyword:"不存在地点XYZ测试", beType:1}` → 接口返回 `code=200`，但**未返回空结果**，而是返回了 5 家城市级兜底门店（含与关键词无关的远距离门店）。
- 因此，**接口成功（code=200）不等于关键词精确匹配成功**。
- 本次仅为单次观察：不推断具体兜底算法，也不推广为所有城市、所有关键词都必然如此。
- 展示要求：门店列表应向用户展示实际地址；位置相关性不明确时提示用户确认；**不得仅凭 `code=200` 声称门店就在目标地点附近**。
- `distance` 数值仍不得标注为米或其他未经验证的单位（同"门店定位限制"）。

### 门店定位限制

- 经纬度实测为 `0.0` 时，**不得用于地图定位、路线规划或距离计算**。
- `distance` 单位未确认，不得标注为米。
- 门店状态字段缺失时，应显示"营业状态未知"，**不能仅凭服务器时间推断门店一定营业**。

## 2. query-meals（已实测 ✅）

- 必填：`storeCode`、`orderType`(1/2)、`beType`(1/2/5/6)。
- 依赖规则：自提(beType=1)→orderType=1 且**不传 beCode**；得来速(beType=5)→orderType=1 且必传 beCode；麦乐送(2)/团餐(6)→orderType=2 且必传 beCode（来自 delivery 工具，本项目未验证）。
- 实测：营业时段 `{storeCode:"1420227", orderType:1, beType:1}` 直接成功，87 商品 / 13 分类。
- 打烊时段同一参数失败：`code=600057`「门店可能已关闭或不在营业时间」。
- 预约路径（已实测）：加 `reservationDate:"2026-10-23 11:00"` 后成功，返回预约时段菜单。
- 返回结构：`categories[].{name, meals[].{code, tags[]}}`、`meals.{code}.{name, image, currentPrice, originalPrice, discountType, canWithOrder, withOrder}`、`frequent`。
- **`currentPrice` 是字符串，单位「元」**（如 `"29"`）。`discountType`/`withOrder` 为 null 时字段省略。
- **菜单含非食品周边**（联名棒球帽、丝巾、痒痒挠等），食品/营养挑战必须过滤。

### 预约模式限制

- 只有在门店返回的预约选项（`reservation=true` 且 `reservationTimeOptions` 有对应时段）和工具实际支持的参数允许时，才可进入预约查询。
- 不得自行编造预约时段；未实际收到成功返回前，**不得声称预约已经成功**。
- `600057` 的真实含义与处理方式见文末"已知错误码"。

## 3. query-meal-detail（已实测 ✅）

- 必填：`storeCode`、`orderType`、`beType`、`code`；自提不传 `beCode`（描述明确"传了会报错"）。
- 实测：`code="9900005466"`（巨无霸三件套）成功，返回 3 个轮次：
  - 轮次1 主堡：默认巨无霸(1100)，`supportModify=true`，特调 5 项（酱/吉士/生菜/酸黄瓜/洋葱粒）全部默认选中，`selectedKey="0-1"`、`unselectedKey="0-0"`。
  - 轮次2 小食：默认中薯条(4810)，可加价换大薯条(+¥2.5)等。
  - 轮次3 饮料：默认可乐中杯(3050)，可加价换麦咖啡类(+¥11.5~15.5)。
- 特调传参规则（Schema 明确）：含 `unselectedKey` 的特调组，**组内所有项都必须传给 calculate-price**，选中项 key=`selectedKey`，未选中项 key=`unselectedKey`。修改特调必须依据真实 `modification` 数据构建参数，不可自行拼造。
- ⚠️ 单位陷阱：`diffPrice`（如 `"+ ¥1.5"`）是**元**字符串；`modification.values[].price`（如 `200`）是**分**。两者不可混用。

## 4. query-store-coupons（已实测 ✅，本次返回为空）

- 必填：`storeCode`（纯数字字符串）、`orderType`、`beType`。
- 实测：深圳测试门店（1420227）自提场景、该账号本次查询返回 `code=200`、`data=[]`。
- **"空列表 = 本次查询没有可用券"仅为本次实测结论**，不得泛化为所有门店、所有用户均无优惠券。
- 券字段（Schema）：`title`、`couponId`、`couponCode`、`tradeDateTime`、`products[].{productName, productCode}`。门槛/适用条件无独立字段，**带券算价尚未实测**，不得宣称已验证。

## 5. calculate-price（已实测 ✅，仅无券单品场景）

- 必填：`storeCode`、`orderType`、`beType`；`items[]`：`productCode`(必填)、`quantity`(≥1)、可选 `couponId`/`couponCode`/`modification`/`roundList`。
- 实测：`items:[{productCode:"1100", quantity:1}]`（无券）→ `price=2900` 分 = 29 元，与菜单 `currentPrice:"29"` 元一致。
- **单位说明（逐项确认）**：
  - 已确认以**分**为单位：`price`、`originalPrice`、`discount`、`productList[].subtotal`（及本次实测中出现的价格字段）。
  - 已确认以**元**为单位：`enjoyed` / `enjoyable` 中的 `realDiscount`。
  - 其他字段必须逐项核实，**不能统一假设单位**。
- 返回还包括：`takeWayList[]`（`code`: "eat-in" 堂食 / "locker-in" 外带，为到店下单必带码——本项目不下单，仅记录）、`enjoyed`/`enjoyable`（`amountType` 1特价/2折扣/3立减）。
- 不执行任何订单创建或优惠券绑定操作。

## 6. list-nutrition-foods（已实测 ✅）

- 无参数。返回全部常见餐品营养成分（能量 kJ/kcal、蛋白质、脂肪、碳水、钠、钙）。
- 只有能可靠匹配到对应商品的数据才参与热量挑战；匹配不到显示"未知"，不得判定达标。

## 7. now-time-info（已无副作用调用成功，Schema 已查看）

- 无参数。返回服务器时间（GMT+8），可用于营业时间守卫（对比 `businessStatus` / `businessEndTime`）。
- 注意：状态字段缺失时不能仅凭此时间推断门店一定营业。

## 已知错误码

| 错误码 | 含义 | 处理 |
| --- | --- | --- |
| 600057 | 门店可能已关闭或不在营业时间 | 检查门店返回的营业状态；允许用户换店；只有预约参数与时段已核实后，才提供预约查询选项。 |

## 测试样例声明

以下仅为开发期实测样例，**不固定、不写死**，每次任务必须现场重查：
- 测试门店：深圳北站站内一店 `storeCode=1420227`（自提）
- 测试商品：巨无霸单品 `code=1100`（29 元）、巨无霸三件套 `code=9900005466`（54.5 元）
