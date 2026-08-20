/*
 * names.js — 品种基础代码 → 中文名（仅用于展示）
 * 浏览器全局，供 index.html / trend.html 共用，避免两页各自重复定义。
 * 注意：本文件是「展示层」数据，刻意不放入 compute.js（计算核心）以保持分层清晰。
 */
var CN = {
  A:"豆一",AG:"沪银",AL:"沪铝",AO:"氧化铝",AP:"苹果",AU:"沪金",B:"豆二",BR:"丁二烯橡胶",
  BU:"沥青",BZ:"纯苯",C:"玉米",CF:"棉花",CJ:"红枣",CS:"玉米淀粉",CU:"沪铜",EB:"苯乙烯",
  EG:"乙二醇",FG:"玻璃",I:"铁矿石",JD:"鸡蛋",JM:"焦煤",L:"塑料",LC:"碳酸锂",LH:"生猪",
  M:"豆粕",MA:"甲醇",OI:"菜油",P:"棕榈油",PF:"短纤",PG:"液化石油气",PK:"花生",PP:"聚丙烯",
  PS:"多晶硅",PX:"对二甲苯",RB:"螺纹钢",RM:"菜粕",RU:"橡胶",SA:"纯碱",SC:"原油",SF:"硅铁",
  SH:"烧碱",SI:"工业硅",SM:"锰硅",SR:"白糖",TA:"PTA",UR:"尿素",V:"PVC",Y:"豆油",ZN:"沪锌"
};
function displayName(base){ return CN[base] ? (base + " " + CN[base]) : base; }
