# 数据约定

`trip_data.py init` 输出不含特定目的地的骨架。按需扩展字段，但保持稳定ID及来源引用；检查器若无法理解扩展结构，应相应更新，不伪造数据适配检查。

| 节点 | 字段 |
|---|---|
| meta | destination,start,end,format(web/pdf/both),language,timezone,version,privacy |
| preferences | travelers,budget,pace,interests,day_start,day_end,accessibility |
| sources[] | id,title,url,checked_on；另可写旅行适用期/支持字段 |
| places[] | id,name,booking{mode,url,steps},fee{amount,currency,basis,status},source_ids |
| days[] | date,title,start,end,stops[{place_id,time,duration_min}],legs[] |
| legs[] | from,to（place ID）,mode,route,duration_min,boarding,fare{amount,currency,basis,status},source_ids |
| passes[] | id,name,validity,coverage,redemption,selections；按真实版本扩充 |
| budget[] | id,label,amount,currency,basis,status,quantity,included_in |
| practical | preparation,immigration,connectivity,payments,transport_cards,luggage,emergency,shopping,return；各为步骤/来源列表 |
| open_questions[] | 待确认事项、复核入口及优先级 |

amount:null表示未知，不是免费。0仅确认免费或无增量。status取confirmed/user_confirmed/estimate/unknown，预算可paid。公开稿不保留私人支付记录；自用账本按用户选择保留，分享时裁剪。included_in引用pass ID，覆盖项目不再次累加。不同currency、basis、quantity不能盲目相加。

boarding写具体操作模式。duration_min是门到门预算，route另写步行/车上时间。from/to对接相邻游览点；中转/住处纳入stops或明确扩展结构。

有来源URL不代表结论已被支持，必须人工核对。每次更新日期/预算/地图/正文共用同一版本。初始化数据不含任何旅客的酒店、航班、金额或预约，换城市重新调研。
