"""A manually edited, source-audited sample, NOT an automated model run.

Requires the live collection captured in output/articles.json. Each passage below
must match an actually retrieved publisher article; missing evidence aborts the build.
"""
from datetime import datetime
import json
from pathlib import Path
from zoneinfo import ZoneInfo
from news_agent.collect import Article
from news_agent.config import load
from news_agent.editorial import validate
from news_agent.render import write

# Match publisher titles, not array positions or invented URLs.
ROWS = [
('russia-ukraine-strike', 'world', '俄军导弹袭击乌克兰住宅楼，BBC报道19人死亡', 5,
 [('Children killed while they slept as Russian missile kills 19 in block of flats',
   'A Russian missile has killed 19 people including five children in an apartment block in northern Ukraine, destroying 30 flats as families slept.')],
 '据BBC报道，俄罗斯导弹10月7日击中乌克兰北部普里卢基一栋住宅楼，造成19人死亡，其中包括五名儿童，30套公寓被毁。当地官员称，袭击发生在居民熟睡时；BBC报道了救援人员在废墟中搜寻遇难者的情况。伤亡数字来自报道所引述的当地信息，不能据此认定所有战区损失均已核实。',
 [('Children killed while they slept as Russian missile kills 19 in block of flats',
   'Moscow made no mention of the attack on Pryluky but said its "massive strike" had targeted military industries in Kyiv and elsewhere.')],
 '报道同时指出，莫斯科没有提及普里卢基这次袭击，而称其“大规模打击”针对基辅及其他地区的军事工业设施。简报保留双方说法的归属，不把俄方对整体行动的说明当作对该住宅楼袭击的回应，也不把乌方有关袭击动机的判断写成已证实事实。'),
('yemen-conflict', 'world', '也门战事扩大：政府军公布战果，沙特报告机场遇袭', 5,
 [('Yemeni government forces claim 1,860 Houthis ‘neutralised’',
   'Yemeni government forces said they have “neutralised” 1,860 Houthi fighters since launching a large-scale counter-offensive to retake territory under control of the rebel group.')],
 '半岛电视台报道，也门政府军声称，在旨在夺回胡塞武装控制地区的大规模反攻中，已“消除”1,860名胡塞武装人员。这一数字及措辞来自政府军自身通报，简报不将其改写为经独立核实的死亡人数。政府军称，相关行动是持续进行的“也门黎明”行动的一部分。',
 [('Saudi Arabia confirms three dead in Houthi strikes on its airports',
   'Saudi Arabia has confirmed that Houthi strikes on two of its international airports have killed three people and injured at least 36 others. Fighting between the Houthis and Yemen’s Saudi-backed, and internationally recognised, government has displaced more than 200,000 people.')],
 '同一媒体另一篇报道引述沙特方面称，胡塞武装袭击两座国际机场，造成三人死亡、至少36人受伤。报道称，胡塞武装与获得沙特支持、受国际承认的也门政府之间的战事已导致超过20万人流离失所。两篇报道合并为一条战事新闻，避免在同一期内重复展开同一轮冲突。'),
('us-markets-oil', 'economics', '美股收低，油价在供应担忧与储备释放信号之间波动', 5,
 [('US stocks slide as oil prices fluctuate over renewed Iran war fears',
   'Wall Street closed lower on Wednesday as oil prices rose then fell due to renewed concerns about disruption to Middle East supplies.')],
 '据半岛电视台报道，美国股市周三收低，国际油价则先升后跌。报道将市场波动与中东石油供应可能受到干扰的担忧联系起来。这里呈现的是报道对当日交易的解释，不将单日涨跌推演为未来市场方向，也不据此提供投资建议。',
 [('US stocks slide as oil prices fluctuate over renewed Iran war fears',
   'Oil prices initially climbed on Wednesday following a warning that Iran appeared to be stepping up attacks on tankers in the Strait of Hormuz, before closing lower after International Energy Agency (IEA) member states said they were ready to release more strategic reserves.')],
 '报道说，有关伊朗可能加大对霍尔木兹海峡油轮袭击的警告一度推高油价；国际能源署成员国随后表示准备释放更多战略储备，油价最终回落。这些是风险警告和储备释放意向，不能等同于所有袭击已被证实，或新增储备已经实际投放市场。'),
('eu-china-trade', 'economics', '中欧在北京展开贸易磋商，汽车进口与关键矿产成焦点', 5,
 [('EU-China trade talks begin in Beijing amid escalating pressure',
   'European Trade Commissioner Maros Sefcovic has arrived in Beijing for talks on the European Union’s (EU) growing trade deficit with China.'),
  ('EU negotiators head to China hoping to curb cheap imports of hybrid electric cars',
   'Trade commissioner Maroš Šefčovič and his team fly out on Wednesday and will be negotiating up to the wire in talks scheduled to start the following day and continue late into Friday.')],
 '半岛电视台与《卫报》均报道，欧盟贸易委员马罗什·谢夫乔维奇率团赴北京开展贸易磋商，谈判安排在周四和周五。两篇报道均涉及欧盟对中欧贸易失衡的关切。《卫报》重点关注混合动力汽车进口；半岛电视台还提到稀土和其他关键矿产的出口限制。',
 [('EU-China trade talks begin in Beijing amid escalating pressure',
   'Sefcovic will meet Chinese Commerce Minister Wang Wentao on Thursday and Friday after months of discussions over the EU’s trade deficit of more than €1bn ($1.12bn) daily, as well as Chinese curbs on exports of rare earths and other critical minerals.')],
 '半岛电视台称，谢夫乔维奇将与中国商务部长王文涛会谈。此次磋商承接了此前数月围绕贸易逆差及关键矿产出口限制的讨论。简报将此作为仍在推进的谈判报道，不把欧方希望获得的进口约束措施写成中方已同意的政策，也不将谈判目标误写为达成协议。'),
('us-government-ad-lawsuit', 'politics', '美国民主党起诉特朗普，质疑政府出资广告的政治用途', 4,
 [('Democrats sue US President Trump over taxpayer-funded ad campaign',
   'The Democratic National Committee has filed a lawsuit against United States President Donald Trump over television advertisements that were publicly funded and allegedly used to promote his political policies.')],
 '半岛电视台报道，美国民主党全国委员会已就一批由公共资金支付的电视广告起诉总统特朗普，指控这些广告被用于宣传其政治政策。报道还称，民主党领导人认为广告有助于共和党在11月3日中期选举中的选情。这些内容属于原告的主张，不能表述为法院已经认定违法。',
 [('Democrats sue US President Trump over taxpayer-funded ad campaign',
   'Later that day, Common Cause, a democracy watchdog group, filed a second lawsuit over the same set of ads. It argued that the ads were “overtly political” and therefore ran afoul of laws that bar public funds from being used for political propaganda.')],
 '报道称，监督组织Common Cause同日就同一批广告提起另一宗诉讼，认为其具有明显政治性质，触及禁止公共资金用于政治宣传的法律规定。两宗诉讼围绕同一争议，合并在本条呈现；提起诉讼本身并不代表原告胜诉或相关事实争议已获司法解决。'),
('china-laos-facility', 'politics', '卫星图像显示老挝中方军事设施有飞机部署，中方称不针对第三方', 4,
 [('Satellite images show attack jets at Chinese military facility in Laos',
   'Images provided by the commercial satellite provider Vantor show eight light attack aircraft positioned at Ban Keun airport alongside what appear to be more than a dozen military vehicles lined up in rows.')],
 '《卫报》报道，商业卫星公司Vantor提供的图像显示，老挝班根机场一处新的中方军事设施停有八架轻型攻击机，旁边还出现疑似军用车辆。车辆识别在原报道中带有不确定性；简报保留这一限定，不将图像直接解释为某项作战任务或即将发生的军事行动。',
 [('Satellite images show attack jets at Chinese military facility in Laos',
   'New ‘support and training centre’ prompts concern in region but China says it is ‘not directed at any third party’')],
 '报道将该设施称为新的“支援和训练中心”，并记载中国方面称其“不针对任何第三方”。这一表态与报道所述地区关切一并呈现。卫星图像能够提供设施和装备的观察线索，但单凭这些图像不足以独立确认具体部署意图；有关用途应按报道中的解释和表态分别归属。'),
('boots-acquisition', 'business', '加拿大韦斯顿家族收购Boots，交易金额约67亿英镑', 4,
 [('Boots sold in £7bn deal to Canadian billionaire family',
   "Boots, the High Street pharmacy and retail chain, has been sold in an $8.9bn (£6.7bn) deal to Canada's billionaire Weston family." )],
 'BBC报道，英国药房及零售连锁Boots以89亿美元、约67亿英镑的交易出售给加拿大韦斯顿家族。控股公司Wittington Investments确认了收购安排，卖方为美国私募股权公司Sycamore Partners及佩西纳家族。简报使用正文所列的较精确金额，不把标题中的约70亿英镑当作另一笔交易。',
 [('Boots sold in £7bn deal to Canadian billionaire family',
   'It has closed hundreds of branches across the UK in recent years, leaving it with about 1,800 stores and 51,000 employees, but remains a familiar British brand.')],
 '报道称，Boots近年关闭了英国数百家分店，目前仍约有1,800家门店和51,000名员工。其业务覆盖药房及健康美容等零售领域。以上门店和员工数据提供交易规模的背景，并不意味着收购方已承诺保留全部岗位，也不能据此预测消费者价格或具体门店安排将如何变化。'),
('us-military-execution', 'politics', '特朗普批准胡德堡枪击案犯的枪决安排', 4,
 [("Trump approved the military's 1st firing squad execution since WWII. Why now?",
   'President Trump has approved the execution by firing squad of Nidal Hasan , the former U.S. Army psychiatrist who killed 13 people in a shooting rampage at Fort Hood, Texas, in 2009.')],
 'NPR报道，特朗普已批准对尼达尔·哈桑实施枪决。哈桑原为美国陆军精神科医生，在2009年得克萨斯州胡德堡枪击案中杀害13人。报道说，这将是美国军方六十多年来首次执行死刑，也是二战以来首次采用枪决；上述历史比较按NPR报道呈现。',
 [("Trump approved the military's 1st firing squad execution since WWII. Why now?",
   "Secretary of the Army Adam Telle said in an order released Tuesday that Hasan's execution will take place at Fort Hood on Dec. 3."),
  ("Trump approved the military's 1st firing squad execution since WWII. Why now?",
   'But Hasan could delay those proceedings if he files a habeas corpus appeal in the federal courts, said Robin Maher, executive director of the nonprofit Death Penalty Information Center.')],
 '报道引述陆军部长公布的命令称，执行安排在12月3日、地点为胡德堡。死刑信息中心负责人指出，若哈桑向联邦法院提起人身保护令相关申诉，程序仍可能延后。因此，简报将12月3日写为公布的计划日期，而不写为执行已经发生或日期绝不会改变。'),
('canada-assisted-dying', 'politics', '加拿大拟无限期暂停向仅患精神疾病者开放辅助死亡', 4,
 [('Canada suspends plans to expand assisted dying to people with mental illness',
   'Canada says it will indefinitely suspend plans to expand its medically assisted dying law to people whose sole condition is mental illness, citing a lack of consensus on who would be eligible.'),
  ('Canada to indefinitely bar mental illness as sole reason for access to euthanasia',
   'Under the current rules, people whose sole underlying medical condition is a mental illness have been barred from accessing medical assistance in dying (Maid) to end their lives.')],
 'BBC与《卫报》报道，加拿大政府拟通过立法，继续排除仅以精神疾病为基础病况的辅助死亡申请。BBC称，政府计划无限期暂停这一扩展，理由是对适用资格缺乏共识；《卫报》说明，按现行规则，这一群体本来就不具有相关资格。新表态涉及是否扩大适用范围，而非取消整个制度。',
 [('Canada suspends plans to expand assisted dying to people with mental illness',
   'Wednesday\'s announcement means that Canadians with mental illness as their sole condition will not be able to access assisted dying by March 2027 as previously planned. The government will instead introduce a new law in the coming weeks that suspends that expansion indefinitely, Fraser said.')],
 'BBC称，原定2027年3月开放的安排将不再按原计划推进，司法部长表示政府会在未来数周提出新法。简报区分政府宣布的立法计划与法律已经完成修改的状态；对资格、医疗权利和程序的争议不作价值判断，也不把这一政策消息当作个人医疗建议。'),
('france-school-protests', 'politics', '法国暂停在学生抗议中使用震爆手榴弹，伤害事件仍待调查', 4,
 [('France halts use of stun grenades after boy\'s hand blown off in student protests',
   "France has suspended the use of stun grenades for policing student protests that have swept the country, after a 15-year-old's hand was blown off earlier this week."),
  ('French police suspend use of stun grenades at school protests as minister rejects accusations of brutality',
   'France’s interior minister has suspended the use of stun grenades by police at high school demonstrations but rejected mounting accusations of police brutality during two weeks of protests marred by often violent clashes that have injured hundreds.')],
 'BBC与《卫报》报道，法国在一名15岁学生于抗议中失去一只手后，暂停警方在高中生示威中使用震爆手榴弹。内政部长表示，暂停将持续到相关事实得到澄清。报道中的暂停针对这类学生抗议场景，不等于法国已全面禁止所有警务行动使用同类装备。',
 [('France halts use of stun grenades after boy\'s hand blown off in student protests',
   'Authorities have said he picked up the grenade which then exploded, but students have alleged he was hit directly after an officer fired.')],
 'BBC记载，当局称该学生拾起手榴弹后发生爆炸，而学生一方声称他是被警员发射的手榴弹直接击中。两种说法存在实质差异，简报保留归属而不代替调查下结论。此次争议发生于要求改善学校条件的示威期间；有关执法是否相称，需要结合调查结果判断。'),
('uk-rate-convictions', 'economics', '英国上诉法院撤销五名前巴克莱交易员的定罪', 3,
 [('Ex-bankers jailed for rigging rates have convictions quashed',
   'Five former Barclays traders sentenced in one of the biggest scandals of the financial crisis have had their convictions overturned following a long-running legal battle.')],
 'BBC报道，五名前巴克莱交易员在长期法律争议后，其定罪被英国上诉法院撤销。这些人员此前因操纵银行间贷款相关利率而被判刑。报道还指出，另有两名前伦敦金融城交易员于去年获撤销定罪，为其他人提出上诉铺平了道路。',
 [('Ex-bankers jailed for rigging rates have convictions quashed',
   'The prosecutions were over the manipulation of two key interest rate mechanisms: Libor and Euribor, which at the time were used to set borrowing costs on a range of loans such as mortgages and car finance deals.')],
 '相关起诉涉及Libor和Euribor两项利率机制，当时这些机制被用于确定包括房贷和汽车贷款在内的借款成本。这说明案件为何涉及广泛金融业务，但本条不据此推导贷款合同已失效、所有利率操纵案件均被推翻，或所有涉案人员都拥有相同的司法结果。'),
('brazil-election', 'politics', '巴西总统选举进入第二轮，里约出现反博索纳罗示威', 4,
 [('‘No to the father, no to the son’: Thousands march in Rio against Bolsonaro',
   'Thousands of people have taken to the streets of Rio de Janeiro in a student-led protest against presidential candidate Flavio Bolsonaro and the growing influence of Brazil’s far right.')],
 '半岛电视台报道，数千人在里约热内卢参加由学生发起的示威，反对总统候选人弗拉维奥·博索纳罗。报道称，他在首轮投票中领先现任总统卢拉，两人将于10月25日进行第二轮投票。示威参加者的政治立场按报道归属，不把他们的判断当作全体巴西选民的共同意见。',
 [('‘No to the father, no to the son’: Thousands march in Rio against Bolsonaro',
   'Since neither candidate surpassed the 50 percent threshold, they will face each other in a run-off on October 25.'),
  ('‘Another coup d’état’: fears grow as Flávio Bolsonaro vows to ‘re-democratise’ Brazil',
   'Flávio, 45, beat Lula, 80, in Sunday’s presidential election first round and goes into the runoff on 25 October as favourite.')],
 '《卫报》也报道了首轮结果及10月25日第二轮的安排。两篇报道中卢拉的得票比例表述不一致，因此本样刊不采用该具体比例，也不将其四舍五入后拼成一个所谓“核实数字”。选举尚未完成，首轮领先不等于已当选；本条聚焦后续投票安排及已经发生的示威。')]


# Keep the delivered sample in a news-reading style; reserve software/audit notes for metadata.
COPY = {
'russia-ukraine-strike': (
'据BBC报道，10月7日，一枚俄罗斯导弹击中乌克兰北部普里卢基的住宅楼，造成19人死亡，其中包括五名儿童，30套公寓被毁。当地官员称，袭击发生在居民熟睡时。救援人员在废墟中搜寻遇难者，BBC报道的伤亡数字随救援推进而更新。',
'BBC称，莫斯科未提及普里卢基这次袭击，而表示其“大规模打击”针对基辅及其他地区的军事工业设施。乌方对住宅楼遭袭的描述与俄方对整体行动的说明，分别代表不同来源的说法；该住宅楼袭击的具体情况按BBC所引述的当地信息呈现。'),
'yemen-conflict': (
'半岛电视台报道，也门政府军称，自发动夺回胡塞武装控制地区的大规模反攻以来，已“消除”1,860名胡塞武装人员。政府军称相关战果属于持续进行的“也门黎明”行动。这一数字出自交战一方，“消除”的措辞也不直接等同于经独立核实的死亡人数。',
'同一媒体另文引述沙特方面称，胡塞武装袭击两座国际机场，造成三人死亡、至少36人受伤。报道称，胡塞武装与获得沙特支持、受国际承认的也门政府之间的战事已导致超过20万人流离失所。机场袭击、反攻和民众流离失所，反映了这一轮战事的不同层面。'),
'us-markets-oil': (
'半岛电视台报道，美国股市周三收低，国际油价则先升后跌。报道将当日市场波动与中东石油供应可能受到干扰的担忧联系起来。油价的变化发生在有关地区冲突及能源运输风险的消息持续影响交易之际，股市和能源市场均出现波动。',
'报道称，有关伊朗可能加大对霍尔木兹海峡油轮袭击的警告一度推高油价；国际能源署成员国随后表示，准备释放更多战略储备，油价最终回落。报道中的释放储备属于成员国表达的准备意向，并非确认新增储备已全部实际投放市场。'),
'eu-china-trade': (
'半岛电视台与《卫报》均报道，欧盟贸易委员马罗什·谢夫乔维奇率团赴北京开展贸易磋商，谈判安排在周四和周五。两家媒体均关注欧盟对中欧贸易失衡的关切。《卫报》重点报道混合动力汽车进口议题，半岛电视台还提到稀土和其他关键矿产的出口限制。',
'半岛电视台称，谢夫乔维奇将与中国商务部长王文涛会谈。双方此前已就欧盟对华贸易逆差、稀土及其他关键矿产出口限制讨论数月。此次消息的重点是谈判启动和具体议题；相关报道没有提供已达成最终贸易协议的确认。'),
'us-government-ad-lawsuit': (
'据半岛电视台报道，美国民主党全国委员会就一批由公共资金支付的电视广告起诉总统特朗普，指控这些广告被用于宣传其政治政策。民主党领导人认为，广告旨在帮助共和党在11月3日中期选举中的选情。这一动机判断来自原告方面。',
'报道说，监督组织Common Cause同日就同一批广告提出另一宗诉讼，认为其具有明显政治性质，触及禁止公共资金用于政治宣传的法律规定。两宗案件针对的是同一批广告的资金用途和政治性质；报道所述指控仍属于待法院处理的诉讼主张。'),
'china-laos-facility': (
'《卫报》报道，商业卫星公司Vantor提供的图像显示，老挝班根机场一处新的中方军事设施停有八架轻型攻击机，旁边还出现疑似军用车辆。原报道对车辆识别使用了不确定措辞，关于飞机及车辆的描述均基于报道所引用的卫星观察。',
'报道将这一设施称为新的“支援和训练中心”，称其引发地区关切，同时记载中国方面表示设施“不针对任何第三方”。卫星图像反映的是设施和装备的可见情况，而中方表态说明的是其公开宣称的用途，两者在本条中分别归属。'),
'boots-acquisition': (
'BBC报道，英国药房及零售连锁Boots以89亿美元、约67亿英镑的交易出售给加拿大韦斯顿家族。Wittington Investments确认收购安排，卖方为美国私募股权公司Sycamore Partners及佩西纳家族。这笔交易使英国知名零售连锁再次迎来所有权变更。',
'报道说，Boots近年关闭了英国数百家分店，目前仍约有1,800家门店和51,000名员工。Boots的业务已从药房扩展至健康美容产品及其他零售商品。其门店网络和员工规模，是理解此次收购涉及企业体量的重要背景。'),
'us-military-execution': (
'NPR报道，特朗普已批准对尼达尔·哈桑实施枪决。哈桑原为美国陆军精神科医生，在2009年得克萨斯州胡德堡枪击案中杀害13人。报道说，这将是美国军方六十多年来首次执行死刑，也是二战以来首次采用枪决。',
'报道引述陆军部长公布的命令称，执行计划定于12月3日、地点为胡德堡。死刑信息中心负责人指出，若哈桑向联邦法院提出人身保护令相关申诉，程序仍可能延后。因此，公布的执行日程仍存在因后续司法程序而调整的可能。'),
'canada-assisted-dying': (
'BBC与《卫报》报道，加拿大政府拟通过立法，继续排除仅以精神疾病为基础病况的辅助死亡申请。BBC称，政府计划无限期暂停这一扩展，理由是对适用资格缺乏共识；《卫报》说明，按现行规则，这一群体原本就不具有相关资格。',
'BBC称，原定2027年3月开放的安排将不再按原计划推进，司法部长表示政府将在未来数周提出新法。这次宣布涉及辅助死亡制度是否扩大至仅患精神疾病的人群，消息所述状态是政府准备推动立法，尚非所有法定修改已经完成。'),
'france-school-protests': (
'BBC与《卫报》报道，法国在一名15岁学生于抗议中失去一只手后，暂停警方在高中生示威中使用震爆手榴弹。内政部长表示，暂停将持续到相关事实得到澄清。政府同时对部分有关警方施暴的指控提出反驳。',
'BBC记载，当局称该学生拾起手榴弹后发生爆炸，而学生一方声称他是被警员发射的手榴弹直接击中。两种说法存在实质差异，事件具体经过仍待查明。此次争议发生在要求改善学校条件的示威期间，警方的执法方式因伤害事件受到关注。'),
'uk-rate-convictions': (
'BBC报道，五名前巴克莱交易员在长期法律争议后，其定罪被英国上诉法院撤销。这些人员此前因操纵银行间贷款相关利率而被判刑。报道还指出，两名其他前伦敦金融城交易员于去年获撤销定罪，为其他涉案人员提出上诉铺平了道路。',
'相关起诉涉及Libor和Euribor两项利率机制。当时，这些机制被用于确定包括房贷和汽车贷款在内的一系列借款成本。案件既涉及个别交易员的刑事定罪，也与金融危机期间受到公众关注的利率基准争议有关，本次消息集中于五人的上诉结果。'),
'brazil-election': (
'半岛电视台报道，数千人在里约热内卢参加由学生发起的示威，反对总统候选人弗拉维奥·博索纳罗。报道称，他在首轮投票中领先现任总统卢拉，两人将于10月25日进行第二轮投票。示威发生在首轮结果公布后，反映了部分群体对选举走势的反应。',
'《卫报》也报道了首轮结果及10月25日第二轮的安排。由于首轮没有候选人超过当选所需的半数门槛，选举尚未产生最终胜者。不同报道对卢拉的具体得票比例表述不一致，本样刊因此保留两家媒体一致的第二轮安排，而不采用存在分歧的比例。')}


NEW_ROWS = [
('uk-inheritance-tax-proposal', 'economics', '英国保守党提出家庭住房遗产税减免计划', 4,
 [('Badenoch says Tories would scrap inheritance tax on family homes',
   'Conservative Party leader Kemi Badenoch has pledged to scrap inheritance tax (IHT) on family homes while also allowing couples to leave £1m tax-free, in her keynote speech at the party\'s conference in Birmingham.')],
 'BBC报道，英国保守党领袖凯米·巴德诺赫在伯明翰的党代会演讲中提出，若保守党执政，将取消家庭住房的遗产税，并允许夫妇额外留下100万英镑的免税财产。这是一项反对党提出的税收政策承诺，尚不是已经生效的税制调整。',
 [('Badenoch says Tories would scrap inheritance tax on family homes',
   'The Conservatives have estimated the policy would cost around £6bn a year and believe they have identified £71bn of savings that can be made to government spending, including welfare cuts.')],
 '报道称，保守党估计这项政策每年约需60亿英镑，并认为已找到可削减政府支出的项目，其中包括福利支出。减税成本和节支估算均来自该党。政策涉及财产传承与公共财政之间的取舍；目前应区分政党提出的方案与政府实际采用的政策。'),
('samsung-earnings-guidance', 'business', '三星预计季度营业利润同比增至九倍，芯片需求推动增长', 4,
 [('AI chip boom pushes Samsung profits to record $80bn',
   'Samsung Electronics says it expects a nine-fold surge in its quarterly profits compared with a year earlier, driven by surging demand for memory chips used in artificial intelligence (AI) data centres. The tech giant estimates that its operating profit for the three months to the end of September will jump to 107.4tn won (£61bn; $80bn), its fourth quarter in a row of record earnings.')],
 'BBC报道，三星电子预计第三季度营业利润将达到107.4万亿韩元，约800亿美元，同比增至九倍，主要受到AI数据中心存储芯片需求增长推动。该数字是公司发布的业绩预估，不能写成完整季度财报已经确认的最终利润。',
 [('AI chip boom pushes Samsung profits to record $80bn',
   "The firm's full third-quarter earnings will be released at the end of October. Major South Korean companies tend to release previews of their earnings to advise investors ahead of more detailed reports.")],
 '三星预计在10月底公布完整第三季度财报。BBC说明，韩国大型公司通常先向投资者提供业绩预览，再发布更详细的报告。本条关注的是最新利润指引和存储芯片业务表现，而非重复介绍AI技术原理；收入结构、最终利润及业务细节仍以完整财报为准。'),
('royal-mail-restructuring', 'business', '英国皇家邮政计划到2027年底削减2,500个支持岗位', 4,
 [('Royal Mail plans to cut 2,500 jobs',
   'Royal Mail has announced plans to cut 2,500 head office and other supporting roles by the end of 2027 as it battles competition and falling demand for letter deliveries. The cuts at the postal service will represent about 2% of the 131,000-strong workforce. However, frontline postal workers - posties and drivers - are not part of the proposed restructuring.')],
 'BBC报道，英国皇家邮政宣布，拟在2027年底前削减2,500个总部及其他支持岗位，约占其13.1万名员工的2%。拟议调整不包括一线邮递员和司机。公司将此作为应对竞争和信件投递需求下降的重组计划，消息所述是计划而非已经完成的裁员。',
 [('Royal Mail plans to cut 2,500 jobs',
   'Royal Mail said the workforce reduction, designed to improve efficiency, would be achieved through voluntary redundancies and people choosing to leave the company.'),
  ('Royal Mail plans to cut 2,500 jobs',
   'Royal Mail said it was in formal consultation with its unions, the Communication Workers Union (CWU) and Unite CMA, over the plans.')],
 '皇家邮政表示，将通过自愿离职及员工自行离开实现人员减少，目的是提高效率，并已就计划与工会正式磋商。公司希望以此改善运营，但工会对方案提出批评。理解这条消息应区分公司解释、劳资磋商状态和最终执行结果，不能将计划等同于所有受影响员工立即失业。'),
('japan-beer-competition-probe', 'business', '日本竞争机构搜查四大啤酒企业，调查涉嫌协同涨价', 4,
 [('Japan beer giants raided over alleged price-fixing cartel',
   "Japanese officials have raided the country's biggest beer makers over allegations they worked together to raise the price of their beverages. Asahi, Sapporo, Kirin and Suntory Spirits confirmed to the BBC that their premises had been searched by the Japan Fair Trade Commission (JFTC), adding that they would fully cooperate with the regulator.")],
 'BBC报道，日本公平交易委员会搜查了朝日、札幌、麒麟和三得利烈酒的场所，调查这些企业涉嫌协同提高饮料价格的行为。四家公司向BBC确认搜查，并表示将配合监管机构。调查已展开并不意味着相关企业已经被认定违反反垄断法。',
 [('Japan beer giants raided over alleged price-fixing cartel',
   'According to the Japan Times, the investigation centres on the companies raising their prices in April last year and in October 2022. All four companies announced increases, citing the rising cost of raw materials as well as other factors such as energy and transportation.')],
 'BBC引述《日本时报》称，调查重点涉及这些企业在去年4月和2022年10月的涨价安排。企业当时解释，涨价与原材料、能源及运输等成本上升有关。本条的新进展是监管搜查，而不是把几年前的涨价当作今天刚发生的事件；最终违法与否仍有待调查结论。'),
('microsoft-surface-windows-event', 'technology', '微软发布新Surface笔记本，并介绍Windows更新方向', 4,
 [('Microsoft event debuts new AI-friendly hardware and Windows changes',
   'In its first live event in two years, Microsoft today announced its newest Surface laptop, outlined a host of changes coming to Windows 11, and shared a vision of how local-AI and agentic workflows could reshape personal computing for those in the dev community as well as home enthusiasts.')],
 'Ars Technica报道，微软举行两年来首次现场活动，公布新的Surface笔记本，介绍Windows 11的多项变化，并说明本地AI和智能体工作流程的个人电脑发展方向。报道呈现的是公司新发布的产品及路线说明，不意味着这些设想已全部成为现有系统功能。',
 [('Microsoft event debuts new AI-friendly hardware and Windows changes',
   "Originally teased in May 2026 , the new Surface Laptop Ultra will be Microsoft's first offering to take advantage of the new Nvidia RTX Spark SoC (system on a chip). The device has a starting price of $2,599, and comes in various SoC and memory configurations, with either a 5120-core or 6144-core Blackwell GPU and up to 128GB of LPDDR5x unified memory. It will begin shipping on October 16 and is available for pre-order now.")],
 '报道称，Surface Laptop Ultra采用英伟达RTX Spark芯片，起售价2,599美元，最高提供128GB统一内存，已开放预订，计划10月16日开始发货。产品此前在5月被预告，今天的具体价格、配置和发货安排才是本条关注的新信息，上市后的实际表现仍需后续验证。'),
('google-synthid-detector-release', 'technology', '谷歌扩大SynthID检测支持，并推出专用检测网站', 4,
 [('Google rolls out improved SynthID AI content detector, now available globally',
   "Google has announced that its SynthID detector now supports watermarks from all its partners, and it's available for anyone to use on a new dedicated website.")],
 'Ars Technica报道，谷歌宣布扩大SynthID检测器的支持范围，使其能够识别合作伙伴采用的水印，并通过新的专用网站向公众提供检测。新进展是检测工具的可用性和兼容范围扩大，不能理解为该工具已经能够识别互联网上所有AI生成内容。',
 [('Google rolls out improved SynthID AI content detector, now available globally',
   'SynthID is an invisible signal encoded in the pixels of AI-generated images and videos, and in the waveform of AI audio.'),
  ('Google rolls out improved SynthID AI content detector, now available globally',
   "A major limitation of Google's previous detector was that it only checked for Google's version of SynthID. Even though ChatGPT images, for example, have SynthID, they wouldn't be flagged in Google's detector. That's no longer a problem.")],
 'SynthID通过在图片或视频像素、音频波形中嵌入隐形信号来标记AI内容。报道称，此前的谷歌检测器只检查谷歌自身版本的水印，部分合作方内容即便带有SynthID也不会被识别。此次更新针对的是这一兼容问题，水印检测本身并不是对内容真实性的全面鉴定。')]

# Retain three politics/international, three economics, four companies and two technology events.
KEEP = {'russia-ukraine-strike', 'us-government-ad-lawsuit', 'china-laos-facility',
        'us-markets-oil', 'eu-china-trade', 'boots-acquisition'}
ROWS = [row for row in ROWS if row[0] in KEEP] + NEW_ROWS

def main():
    config = load('config.yaml')
    articles = [Article(**a) for a in json.loads(Path('output/articles.json').read_text())]
    titles = {a.title: a for a in articles}
    date = datetime.fromisoformat(articles[0].retrieved).astimezone(ZoneInfo('America/New_York')).date().isoformat()
    as_of = articles[0].retrieved
    concise = json.loads(Path('samples/concise-copy.json').read_text())
    stories = []
    for key, category, headline, impact, first_evidence, first, second_evidence, second in ROWS:
        first, second = concise.get(key, COPY.get(key, (first, second)))
        claims, ids = [], []
        for text, refs, kind in [(first, first_evidence, 'fact'), (second, second_evidence, 'context')]:
            cites = []
            for title, quote in refs:
                article = titles[title]
                if quote not in article.evidence: raise ValueError(f'Missing verified passage for {title}')
                if article.id not in ids: ids.append(article.id)
                cites.append({'article_id': article.id, 'quote': quote})
            claims.append({'kind': kind, 'text': text, 'evidence': cites})
        independent = key in ('eu-china-trade', 'canada-assisted-dying', 'france-school-protests')
        # Canada context supports same core policy but the Guardian excerpt does not state
        # the new indefinite duration, so don't overstate full corroboration of that detail.
        if key == 'canada-assisted-dying': independent = False
        stories.append({'event_key': key, 'category': category, 'headline': headline, 'article_ids': ids,
            'is_conflict': key == 'russia-ukraine-strike',
            'freshness': {'development': headline, 'article_id': claims[0]['evidence'][0]['article_id'], 'quote': claims[0]['evidence'][0]['quote']},
            'scores': {'consequence': impact, 'timeliness': 4, 'credibility': 4, 'global_relevance': impact},
            'claims': claims, 'cross_check': {
                'status': 'independent' if independent else 'single_source' if len(ids) == 1 else 'not_independent',
                'note': '两家媒体对核心事件有分别报道；补充细节仍按各自来源归属。' if independent else
                        '依据列出的原始报道整理；本条不宣称所有细节均获独立核实。'}})
    edition = {'date': date, 'as_of': as_of, 'stories': stories, 'model': 'assistant-curated-static-sample',
               'editorial_mode': 'manually_curated_source_audit',
               'review': {'approved': True, 'issues': []},
               'sample_note': '这是列明截止时间的新闻样刊，供格式参考。'}
    validate(edition, articles, config, date)
    from news_agent.weather import forecast
    edition['weather'] = forecast(config)
    directory = Path('samples')
    (directory / 'edition.json').write_text(json.dumps(edition, ensure_ascii=False, indent=2))
    # Retain just the short exact supporting excerpts, not full publisher article bodies.
    selected = {aid for s in stories for aid in s['article_ids']}
    excerpts = []
    for a in articles:
        if a.id in selected:
            quotes = list(dict.fromkeys(e['quote'] for s in stories for c in s['claims'] for e in c['evidence'] if e['article_id'] == a.id))
            data = a.to_dict(); data['evidence'] = '\n'.join(quotes)
            excerpts.append(data)
    (directory / 'evidence.json').write_text(json.dumps(excerpts, ensure_ascii=False, indent=2))
    write(edition, '全球每日新闻 · 人工整理样刊', directory, test=True)
    print('Built sample:', len(stories), 'stories,', len(excerpts), 'publisher articles')


if __name__ == '__main__': main()
