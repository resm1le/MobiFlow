package com.example.autoa11y.core.common.keywords

/**
 * Shared keyword pools for plugins.
 *
 * Rules:
 * - Keep property names stable so plugin references stay intact.
 * - Keep lists broad enough for reuse, but coherent enough to fit each domain.
 * - Deduplicate aggressively to avoid repetitive automation patterns.
 */
object CommonKeywords {

    private fun words(vararg items: String): List<String> =
        items.map { it.trim() }.filter { it.isNotEmpty() }.distinct()

    private fun merge(vararg groups: List<String>): List<String> =
        groups.asList().flatten().map { it.trim() }.filter { it.isNotEmpty() }.distinct()

    val ShoppingEn: List<String> = words(
        "milk", "bread", "eggs", "banana", "apple", "orange juice", "coffee", "tea", "rice", "pasta",
        "chocolate", "cookies", "chips", "yogurt", "cheese", "butter", "honey", "peanut butter",
        "iphone", "samsung galaxy", "ipad", "airpods", "smart watch", "laptop", "tablet", "keyboard",
        "mouse", "bluetooth speaker", "phone charger", "power bank", "monitor", "printer",
        "vacuum cleaner", "air fryer", "blender", "toaster", "microwave", "floor lamp", "desk", "office chair",
        "pillow", "bed sheets", "bath towel", "candles", "area rug", "storage containers", "trash bags",
        "t-shirt", "jeans", "hoodie", "winter jacket", "running shoes", "boots", "slippers", "backpack",
        "wrist watch", "sunglasses", "swimsuit", "pajamas", "underwear", "yoga pants",
        "shampoo", "conditioner", "body lotion", "moisturizer", "perfume", "sunscreen", "toothbrush", "lipstick",
        "lego set", "stuffed animal", "toy car", "board game", "dog toy", "cat food", "dog food"
    )

    /**
     * Fashion / accessories / room decor / toy searches suited to visual shopping apps.
     * This is the primary reusable pool for SHEIN-like plugins.
     */
    val fashionShoppingEn: List<String> = words(
        "dress", "maxi dress", "mini dress", "yellow dress", "black dress", "floral dress",
        "women summer dress", "vacation dress", "party dress", "bodycon dress", "satin dress",
        "hoodie", "zip hoodie", "oversized hoodie", "women sweater", "cardigan", "knit top",
        "blouse", "crop top", "tank top", "graphic tee", "wide leg pants", "cargo pants",
        "matching pajamas", "cute pajamas", "sleepwear set", "loungewear set", "robe",
        "crossbody bag", "shoulder bag", "cute bag", "mini backpack", "wallet",
        "hair clips", "claw clip", "headband", "earrings", "necklace", "bracelet", "ring set",
        "phone case", "tablet case", "makeup bag", "travel pouch", "cosmetic organizer",
        "slippers", "sandals", "sneakers", "ankle boots", "socks", "fuzzy socks",
        "kawaii accessories", "coquette accessories", "minimalist jewelry", "boho jewelry",
        "stationery", "journal", "sticker pack", "desk organizer", "pen holder",
        "office decor", "room decor", "bedroom decor", "dorm decor", "vanity decor",
        "minimalist decor", "cute decor", "wall art", "mirror", "fairy lights",
        "blanket", "throw blanket", "pillow cover", "cushion cover", "bedding set",
        "kitchen organizer", "drawer organizer", "storage basket", "laundry basket",
        "toy", "kids toy", "plush toy", "fidget toy", "stress relief toy", "sensory toy",
        "squishy", "bread squishy", "mochi squishy", "squeeze cheese", "cute plush",
        "pet clothes", "dog sweater", "cat bed", "baby blanket", "baby accessories"
    )

    val worldCitiesEn: List<String> = words(
        "New York", "Los Angeles", "Chicago", "San Francisco", "Seattle", "Boston", "Miami", "Austin",
        "Toronto", "Vancouver", "Montreal", "Mexico City", "Bogota", "Lima", "Santiago", "Buenos Aires",
        "Sao Paulo", "Rio de Janeiro", "London", "Manchester", "Paris", "Berlin", "Munich", "Frankfurt",
        "Madrid", "Barcelona", "Rome", "Milan", "Amsterdam", "Brussels", "Zurich", "Vienna", "Prague",
        "Warsaw", "Stockholm", "Copenhagen", "Dublin", "Lisbon", "Athens", "Istanbul",
        "Dubai", "Abu Dhabi", "Doha", "Cairo", "Johannesburg", "Cape Town", "Nairobi",
        "Delhi", "Mumbai", "Bengaluru", "Chennai", "Hyderabad", "Karachi", "Dhaka", "Colombo",
        "Bangkok", "Singapore", "Kuala Lumpur", "Jakarta", "Manila", "Hanoi", "Ho Chi Minh City",
        "Tokyo", "Osaka", "Kyoto", "Seoul", "Busan", "Beijing", "Shanghai", "Guangzhou", "Shenzhen",
        "Hong Kong", "Taipei", "Sydney", "Melbourne", "Brisbane", "Auckland"
    )

    val browsingQueriesEn: List<String> = words(
        "google", "youtube", "weather", "gmail", "amazon", "translate", "maps", "news", "calculator",
        "chatgpt", "netflix", "spotify", "reddit", "wikipedia", "ebay", "walmart", "target", "best buy",
        "restaurants near me", "coffee shops", "gas stations nearby", "pharmacy near me", "flights", "hotels",
        "nba scores", "nfl schedule", "bitcoin price", "currency converter", "time in london",
        "java list vs arraylist", "kotlin data class copy", "python virtualenv setup", "docker compose up build",
        "linux check disk space", "rest api best practices", "sql injection prevention", "react useeffect hook",
        "android studio emulator slow", "firebase auth documentation", "mongodb vs postgresql", "redis cache tutorial",
        "pip install requirements.txt", "pandas dataframe to csv", "regex for email validation", "json formatter online",
        "how to tie a tie", "how to boil eggs", "how to take a screenshot on mac", "how to change tire",
        "how to jump start a car", "how to solve a rubiks cube", "how to learn spanish fast", "how to write a cover letter",
        "best smartphones 2026", "macbook air review", "best noise cancelling headphones", "best gaming laptop under 1000",
        "mechanical keyboard switches guide", "best running shoes for flat feet", "gift ideas for dad", "toys for 3 year olds",
        "top movies to watch", "best horror movies on netflix", "popular tiktok songs", "steam sale dates",
        "cheap flights to paris", "hotels in tokyo", "best beaches in florida", "camping spots near me",
        "symptoms of flu vs covid", "benefits of intermittent fasting", "foods high in protein", "normal blood pressure range",
        "define serendipity", "periodic table of elements", "capital of australia", "quadratic equation solver",
        "how to file llc", "business plan template", "seo tips for beginners", "resume templates word",
        "why is the sky blue", "can dogs eat grapes", "fantasy football rankings", "horoscope today"
    )

    val chatQueriesEn: List<String> = words(
        "how is your day going",
        "what are you up to",
        "did you eat yet",
        "how was work today",
        "what are your weekend plans",
        "are you free later",
        "want to grab coffee",
        "want to watch a movie",
        "did you sleep well",
        "how is the weather there",
        "what music are you listening to",
        "have you seen this meme",
        "what are you cooking tonight",
        "how is your family",
        "did you finish the task",
        "can you send the file",
        "what time should we meet",
        "are you on your way",
        "did the package arrive",
        "how was your workout",
        "what are you reading lately",
        "want to play a game later",
        "how did the interview go",
        "any lunch recommendations",
        "did you watch the game",
        "what show are you watching",
        "do you need anything from the store",
        "how is your project going",
        "want to call tonight",
        "have a good night"
    )

    val chatMessagesEn: List<String> = words(
        "Hey!",
        "Good morning",
        "Good night",
        "I am on my way",
        "I just got home",
        "That sounds good",
        "Lets do it",
        "No problem",
        "Thanks!",
        "See you soon",
        "I will text you later",
        "Can you call me when free",
        "I am a bit busy right now",
        "That is hilarious",
        "Hope you have a great day",
        "Take care",
        "I will send it in a minute",
        "Running a little late",
        "Just finished work",
        "Talk later"
    )

    val chatMessagesRu: List<String> = words(
        "Привет",
        "Доброе утро",
        "Спокойной ночи",
        "Я уже в пути",
        "Спасибо",
        "Без проблем",
        "Созвонимся позже",
        "Как дела",
        "Увидимся скоро",
        "Хорошего дня"
    )

    val chatMessagesZh: List<String> = words(
        "你好",
        "早上好",
        "晚安",
        "我到了",
        "我在路上",
        "谢谢",
        "没问题",
        "回头聊",
        "今天天气不错",
        "辛苦了"
    )

    val chatMessagesJa: List<String> = words(
        "こんにちは",
        "おはよう",
        "おやすみ",
        "ありがとう",
        "今向かっています",
        "また後で連絡します",
        "大丈夫です",
        "お疲れさま",
        "了解です",
        "またね"
    )

    val chatMessagesKo: List<String> = words(
        "안녕하세요",
        "좋은 아침",
        "안녕히 주무세요",
        "고마워요",
        "지금 가는 중이에요",
        "나중에 연락할게요",
        "괜찮아요",
        "수고했어요",
        "알겠어요",
        "곧 봐요"
    )

    val chatMessagesAll: List<String> =
        merge(chatMessagesEn, chatMessagesRu, chatMessagesZh, chatMessagesJa, chatMessagesKo)

    val mapsPlacesUnique: List<String> = words(
        "Times Square", "Central Park", "Statue of Liberty", "Empire State Building",
        "Golden Gate Bridge", "Fishermans Wharf", "Pike Place Market", "Space Needle",
        "The White House", "Lincoln Memorial", "Disneyland Park", "Universal Studios Hollywood",
        "Eiffel Tower", "Louvre Museum", "Colosseum", "Trevi Fountain", "Sagrada Familia",
        "Big Ben", "Tower Bridge", "London Eye", "Brandenburg Gate", "Neuschwanstein Castle",
        "Amsterdam Central Station", "Prague Castle", "Acropolis", "Burj Khalifa",
        "Dubai Mall", "Marina Bay Sands", "Gardens by the Bay", "Petronas Twin Towers",
        "Tokyo Station", "Shibuya Crossing", "Tokyo Tower", "Fushimi Inari Shrine",
        "N Seoul Tower", "Gyeongbokgung Palace", "Taipei 101", "Victoria Harbour",
        "The Bund", "Forbidden City", "Tiananmen", "Canton Tower",
        "Sydney Opera House", "Sydney Harbour Bridge", "Auckland Sky Tower",
        "JFK Airport", "LAX Airport", "Heathrow Airport", "Charles de Gaulle Airport",
        "Haneda Airport", "Incheon Airport", "Singapore Changi Airport", "Dubai International Airport"
    )

    val mapsPlacesGeneric: List<String> = words(
        "McDonalds", "Burger King", "KFC", "Subway", "Chipotle", "Dominos", "Pizza Hut", "Starbucks",
        "Dunkin", "Peets Coffee", "Boba Tea", "Smoothie King",
        "Walmart", "Target", "Costco", "Trader Joes", "Whole Foods", "Aldi", "Safeway",
        "Best Buy", "Home Depot", "Lowes", "IKEA", "Macys", "Nordstrom", "Sephora", "Ulta Beauty",
        "Shell Gas Station", "Chevron", "BP Station", "Exxon", "Tesla Supercharger", "ChargePoint",
        "Hilton Hotel", "Marriott Hotel", "Hyatt Hotel", "Holiday Inn", "Motel", "Hostel",
        "CVS Pharmacy", "Walgreens", "Rite Aid", "Urgent Care", "Hospital", "Dentist", "Veterinarian",
        "Bank of America", "Chase Bank", "Wells Fargo", "ATM near me", "Credit Union",
        "UPS Store", "FedEx Office", "Post Office", "Dry Cleaner", "Laundromat", "Car Wash",
        "Hair Salon", "Barbershop", "Gym", "Planet Fitness", "Yoga Studio", "Movie Theater", "Bowling Alley",
        "Park", "Dog Park", "Hiking Trail", "Beach", "Museum", "Aquarium", "Zoo", "Playground",
        "Restaurant", "Coffee shop", "Bakery", "Dessert shop", "Parking garage", "Bookstore"
    )

    val mapsNearbyCategories: List<String> = words(
        "Restaurants", "Coffee", "Gas stations", "Hotels", "Groceries", "Shopping",
        "Parks", "Bars", "Fast food", "Pharmacy", "Banks", "Gym",
        "Hospital", "Parking", "Car wash", "Bakery", "Dessert", "Breakfast",
        "Lunch", "Dinner", "Takeout", "Delivery", "ATM", "Bookstore"
    )

    val amapCityNamesCn: List<String> = words(
        "北京市", "上海市", "天津市", "重庆市",
        "广州市", "深圳市", "佛山市", "东莞市", "中山市", "珠海市", "惠州市", "汕头市",
        "南京市", "苏州市", "无锡市", "常州市", "南通市", "徐州市", "扬州市", "镇江市",
        "杭州市", "宁波市", "温州市", "绍兴市", "嘉兴市", "金华市", "台州市",
        "成都市", "绵阳市", "德阳市", "乐山市", "南充市", "宜宾市",
        "武汉市", "长沙市", "郑州市", "西安市", "济南市", "青岛市", "合肥市", "福州市",
        "厦门市", "泉州市", "南昌市", "昆明市", "贵阳市", "南宁市", "海口市",
        "石家庄市", "太原市", "沈阳市", "大连市", "长春市", "哈尔滨市",
        "兰州市", "西宁市", "银川市", "乌鲁木齐市", "拉萨市",
        "洛阳市", "襄阳市", "宜昌市", "岳阳市", "株洲市", "保定市", "唐山市", "烟台市", "潍坊市"
    )

    val amapPlacesUnique: List<String> = words(
        "北京", "上海", "广州", "深圳", "南京", "杭州", "成都", "武汉", "西安", "长沙",
        "天安门", "故宫", "长城", "颐和园", "天坛",
        "外滩", "东方明珠", "陆家嘴", "南京路步行街",
        "西湖", "灵隐寺", "雷峰塔",
        "兵马俑", "大雁塔", "钟楼",
        "武侯祠", "锦里", "宽窄巷子", "都江堰",
        "黄鹤楼", "东湖", "中山陵", "夫子庙", "玄武湖", "鼓浪屿", "广州塔",
        "布达拉宫", "丽江古城", "张家界", "黄山", "泰山", "九寨沟",
        "北京南站", "北京西站", "上海虹桥站", "南京南站", "杭州东站", "广州南站", "深圳北站",
        "首都机场", "大兴机场", "浦东机场", "虹桥机场", "白云机场", "宝安机场", "双流机场"
    )

    val amapPlacesGeneric: List<String> = words(
        "肯德基", "麦当劳", "星巴克", "瑞幸咖啡", "蜜雪冰城", "喜茶", "奈雪的茶",
        "海底捞", "必胜客", "汉堡王", "德克士", "华莱士", "正新鸡排", "沙县小吃", "兰州拉面",
        "如家酒店", "汉庭酒店", "全季酒店", "亚朵酒店", "维也纳酒店", "希尔顿", "万豪",
        "沃尔玛", "永辉超市", "大润发", "华润万家", "盒马鲜生", "山姆会员店", "名创优品",
        "屈臣氏", "小米之家", "华为旗舰店", "苏宁易购",
        "全家便利店", "罗森", "7-11", "便利蜂",
        "中国银行", "工商银行", "建设银行", "农业银行", "招商银行", "交通银行", "ATM",
        "医院", "药店", "大参林", "益丰大药房", "人民医院", "中心医院",
        "加油站", "中石油", "中石化", "充电站", "停车场", "洗车", "快递站", "菜鸟驿站",
        "理发店", "健身房", "电影院", "KTV", "网咖",
        "万达广场", "龙湖天街", "华润万象城", "印象城", "宜家家居", "迪卡侬",
        "地铁站", "公交站", "高铁站", "汽车站", "机场",
        "美食", "火锅", "烧烤", "奶茶", "蛋糕", "面包店", "日料", "韩餐", "西餐", "早餐", "夜宵"
    )

    val amapNearbyCategories: List<String> = words(
        "美食", "酒店", "景点门票", "加油站", "休闲玩乐", "超市",
        "咖啡厅", "电影院", "KTV", "健身房", "停车场", "药店",
        "银行", "医院", "公园", "书店", "宠物店", "花店",
        "快递", "洗车", "理发", "足浴", "早餐", "夜宵"
    )
}
