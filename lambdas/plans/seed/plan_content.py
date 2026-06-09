"""Seed catalog + per-day content for the v1 reading plans (COMPANION_SPEC.md §9.1).

This is the single source of truth for the reading-plan catalog content. It is
consumed by `seed_plans.py` to load DynamoDB (the `reading_plans` + `reading_plan_days`
tables) and could also be imported by tests. It contains NO AWS calls — just data.

Shapes (camelCase, ADR-1; matches the frontend mock in versiful-frontend/src/mocks):
    catalog item -> { slug, title, description, topic, dayCount, emoji, isActive }
    day item     -> { dayNumber (int), passageRef, theme, prompt }

Passages are *references only* — verse text comes from the model at delivery time,
consistent with the no-scripture-API decision (spec §2, §9.1).
"""

# ---------------------------------------------------------------------------
# Catalog (the 7 v1 plans). `dayCount` is validated against PLAN_DAYS below.
# ---------------------------------------------------------------------------
CATALOG = [
    {
        "slug": "anxiety-7",
        "title": "Finding Peace in Anxiety",
        "description": "Seven days of Scripture for an anxious heart — trading worry for the peace of God.",
        "topic": "anxiety",
        "dayCount": 7,
        "emoji": "🌊",
        "isActive": True,
    },
    {
        "slug": "grief-14",
        "title": "Walking Through Grief",
        "description": "A gentle fourteen-day companion for loss, lament, and the slow return of hope.",
        "topic": "grief",
        "dayCount": 14,
        "emoji": "🕊️",
        "isActive": True,
    },
    {
        "slug": "new-believer-30",
        "title": "First Steps with Jesus",
        "description": "A thirty-day on-ramp to faith — who Jesus is and what it means to follow Him.",
        "topic": "new_believer",
        "dayCount": 30,
        "emoji": "🌅",
        "isActive": True,
    },
    {
        "slug": "forgiveness-7",
        "title": "The Freedom of Forgiveness",
        "description": "Seven days to lay down resentment and walk in the freedom God offers.",
        "topic": "forgiveness",
        "dayCount": 7,
        "emoji": "🔓",
        "isActive": True,
    },
    {
        "slug": "marriage-14",
        "title": "Strengthening Your Marriage",
        "description": "Two weeks of Scripture and prompts to nurture love, patience, and partnership.",
        "topic": "marriage",
        "dayCount": 14,
        "emoji": "💍",
        "isActive": True,
    },
    {
        "slug": "gratitude-7",
        "title": "A Heart of Gratitude",
        "description": "Seven days to cultivate thankfulness and notice God's goodness daily.",
        "topic": "gratitude",
        "dayCount": 7,
        "emoji": "🌾",
        "isActive": True,
    },
    {
        "slug": "hope-10",
        "title": "Holding On to Hope",
        "description": "Ten days anchoring your heart in the steady hope of Christ.",
        "topic": "hope",
        "dayCount": 10,
        "emoji": "⚓",
        "isActive": True,
    },
]

# ---------------------------------------------------------------------------
# Per-day content keyed by slug. Each entry: dayNumber, passageRef, theme, prompt.
# ---------------------------------------------------------------------------
PLAN_DAYS = {
    "anxiety-7": [
        {"dayNumber": 1, "passageRef": "Philippians 4:6-7", "theme": "Bring it to God", "prompt": "What worry can you hand to God in prayer right now, naming it specifically?"},
        {"dayNumber": 2, "passageRef": "Matthew 6:25-34", "theme": "One day at a time", "prompt": "Where are you borrowing tomorrow's worry today? What would it look like to stay in just today?"},
        {"dayNumber": 3, "passageRef": "Matthew 6:26", "theme": "God's provision", "prompt": "Name three ways God has already provided for you this week, even small ones."},
        {"dayNumber": 4, "passageRef": "Psalm 94:19", "theme": "Consolation in anxiety", "prompt": "When anxiety is greatest, where have you felt even a flicker of God's comfort?"},
        {"dayNumber": 5, "passageRef": "1 Peter 5:7", "theme": "He cares for you", "prompt": "Write a sentence to God casting one specific care onto Him."},
        {"dayNumber": 6, "passageRef": "Isaiah 41:10", "theme": "Do not fear", "prompt": "What fear loses some of its grip when you remember God is with you?"},
        {"dayNumber": 7, "passageRef": "John 14:27", "theme": "A peace the world can't give", "prompt": "Looking back over the week, what has shifted in how you carry anxiety?"},
    ],
    "grief-14": [
        {"dayNumber": 1, "passageRef": "Psalm 34:18", "theme": "Near to the brokenhearted", "prompt": "Where do you most need to know God is near today?"},
        {"dayNumber": 2, "passageRef": "Matthew 5:4", "theme": "Blessed are those who mourn", "prompt": "What loss are you carrying? Let yourself name it honestly before God."},
        {"dayNumber": 3, "passageRef": "Psalm 23", "theme": "Through the valley", "prompt": "What does it mean to you that He walks *with* you through this valley, not around it?"},
        {"dayNumber": 4, "passageRef": "Lamentations 3:19-24", "theme": "Yet I have hope", "prompt": "Even in the ache, where can you say 'His mercies are new'?"},
        {"dayNumber": 5, "passageRef": "John 11:33-35", "theme": "Jesus wept", "prompt": "How does it change your grief to know Jesus weeps with you?"},
        {"dayNumber": 6, "passageRef": "Psalm 56:8", "theme": "He keeps your tears", "prompt": "What would you want God to know about how you've been feeling?"},
        {"dayNumber": 7, "passageRef": "2 Corinthians 1:3-4", "theme": "The God of all comfort", "prompt": "Who has comforted you in this season? How might God comfort others through you one day?"},
        {"dayNumber": 8, "passageRef": "Psalm 42:5-6", "theme": "Talking to your soul", "prompt": "Write a few honest words to your own soul, then a few words of hope back."},
        {"dayNumber": 9, "passageRef": "Isaiah 61:1-3", "theme": "Beauty for ashes", "prompt": "What 'ashes' are you holding that you long to see redeemed?"},
        {"dayNumber": 10, "passageRef": "Romans 8:18", "theme": "Not worth comparing", "prompt": "What helps you lift your eyes, even briefly, beyond this present pain?"},
        {"dayNumber": 11, "passageRef": "Revelation 21:4", "theme": "No more tears", "prompt": "What about God's promise of no more death or mourning gives you hope?"},
        {"dayNumber": 12, "passageRef": "Psalm 30:5", "theme": "Joy comes in the morning", "prompt": "Where have you glimpsed even a small return of joy?"},
        {"dayNumber": 13, "passageRef": "John 14:1-3", "theme": "A place prepared", "prompt": "How does the hope of being reunited shape how you grieve?"},
        {"dayNumber": 14, "passageRef": "Psalm 73:26", "theme": "God is my strength", "prompt": "Looking back over two weeks, what has God carried you through?"},
    ],
    "new-believer-30": [
        {"dayNumber": 1, "passageRef": "John 3:16", "theme": "God's love for you", "prompt": "What does it mean to you that God loved the world — including you — enough to give His Son?"},
        {"dayNumber": 2, "passageRef": "John 1:1-14", "theme": "Who Jesus is", "prompt": "Which words used to describe Jesus here stand out most to you, and why?"},
        {"dayNumber": 3, "passageRef": "Romans 3:23", "theme": "Why we need a Savior", "prompt": "What does it free in you to admit you can't earn your way to God?"},
        {"dayNumber": 4, "passageRef": "Romans 6:23", "theme": "The free gift", "prompt": "How does it feel to receive eternal life as a gift rather than a wage?"},
        {"dayNumber": 5, "passageRef": "Ephesians 2:8-9", "theme": "Saved by grace", "prompt": "Where are you still tempted to perform for God's approval?"},
        {"dayNumber": 6, "passageRef": "2 Corinthians 5:17", "theme": "A new creation", "prompt": "What 'old thing' do you sense God making new in you?"},
        {"dayNumber": 7, "passageRef": "John 10:27-30", "theme": "Held secure", "prompt": "What does it mean that no one can snatch you out of His hand?"},
        {"dayNumber": 8, "passageRef": "Romans 8:1", "theme": "No condemnation", "prompt": "What guilt can you lay down today because you're in Christ?"},
        {"dayNumber": 9, "passageRef": "Galatians 5:22-23", "theme": "The fruit of the Spirit", "prompt": "Which fruit of the Spirit do you most long to see grow in you?"},
        {"dayNumber": 10, "passageRef": "John 14:15-17", "theme": "The Holy Spirit", "prompt": "How does it change things to know God's Spirit lives in you?"},
        {"dayNumber": 11, "passageRef": "Matthew 6:9-13", "theme": "How to pray", "prompt": "Try praying through the Lord's Prayer slowly in your own words."},
        {"dayNumber": 12, "passageRef": "Psalm 1", "theme": "Rooted in the Word", "prompt": "What would it look like to 'delight' in Scripture this week?"},
        {"dayNumber": 13, "passageRef": "Hebrews 10:24-25", "theme": "Why community matters", "prompt": "Who could walk this new faith journey alongside you?"},
        {"dayNumber": 14, "passageRef": "Matthew 28:18-20", "theme": "Baptism & following", "prompt": "What's one next step of obedience you sense God inviting you into?"},
        {"dayNumber": 15, "passageRef": "Luke 15:11-24", "theme": "The Father runs to you", "prompt": "Where do you need to know God runs *toward* you, not away?"},
        {"dayNumber": 16, "passageRef": "Psalm 103:8-12", "theme": "How far He removes our sin", "prompt": "What sin do you need to believe God has truly removed 'as far as the east is from the west'?"},
        {"dayNumber": 17, "passageRef": "John 15:1-8", "theme": "Abiding in Jesus", "prompt": "What helps you stay 'connected to the vine' on an ordinary day?"},
        {"dayNumber": 18, "passageRef": "Philippians 4:13", "theme": "Strength in Christ", "prompt": "What are you facing that you need His strength for?"},
        {"dayNumber": 19, "passageRef": "Romans 12:1-2", "theme": "A renewed mind", "prompt": "What pattern of thinking is God inviting you to surrender?"},
        {"dayNumber": 20, "passageRef": "James 1:2-4", "theme": "Trials grow you", "prompt": "How might God be using a current hardship to grow your faith?"},
        {"dayNumber": 21, "passageRef": "1 John 1:9", "theme": "Confession & cleansing", "prompt": "Is there anything you want to confess and receive cleansing for today?"},
        {"dayNumber": 22, "passageRef": "Matthew 11:28-30", "theme": "Rest for your soul", "prompt": "What burden are you carrying that Jesus offers to share?"},
        {"dayNumber": 23, "passageRef": "Psalm 23", "theme": "The Lord is my shepherd", "prompt": "Where do you need the Shepherd to lead you to 'still waters' right now?"},
        {"dayNumber": 24, "passageRef": "Romans 8:31-39", "theme": "Nothing can separate us", "prompt": "What fear shrinks when you remember nothing can separate you from God's love?"},
        {"dayNumber": 25, "passageRef": "Ephesians 6:10-18", "theme": "Standing firm", "prompt": "Which piece of God's armor do you most need today?"},
        {"dayNumber": 26, "passageRef": "Colossians 3:12-14", "theme": "Clothed in love", "prompt": "Which of these — compassion, kindness, patience — could you 'put on' today?"},
        {"dayNumber": 27, "passageRef": "Proverbs 3:5-6", "theme": "Trusting His direction", "prompt": "Where are you leaning on your own understanding instead of trusting Him?"},
        {"dayNumber": 28, "passageRef": "Micah 6:8", "theme": "What God asks of us", "prompt": "What would it look like to 'act justly, love mercy, walk humbly' this week?"},
        {"dayNumber": 29, "passageRef": "1 Corinthians 13:4-7", "theme": "What love looks like", "prompt": "Which line of this description of love challenges you most?"},
        {"dayNumber": 30, "passageRef": "Jeremiah 29:11", "theme": "A future and a hope", "prompt": "Looking back over 30 days, how has your picture of God changed?"},
    ],
    "forgiveness-7": [
        {"dayNumber": 1, "passageRef": "Colossians 3:13", "theme": "Forgive as you were forgiven", "prompt": "Who comes to mind when you think about forgiveness? Just name them before God today."},
        {"dayNumber": 2, "passageRef": "Matthew 18:21-35", "theme": "The unforgiving servant", "prompt": "How does remembering how much you've been forgiven change how you see your own grudge?"},
        {"dayNumber": 3, "passageRef": "Ephesians 4:31-32", "theme": "Letting go of bitterness", "prompt": "What bitterness have you been carrying that's heavier than you realized?"},
        {"dayNumber": 4, "passageRef": "Psalm 103:8-14", "theme": "How God forgives", "prompt": "What would it look like to extend to someone the patience God extends to you?"},
        {"dayNumber": 5, "passageRef": "Matthew 6:14-15", "theme": "Forgiveness and freedom", "prompt": "Forgiving isn't saying it was okay. What weight could you hand to God instead of carrying?"},
        {"dayNumber": 6, "passageRef": "Luke 23:34", "theme": "Father, forgive them", "prompt": "Jesus forgave from the cross. What's the hardest part of forgiveness for you right now?"},
        {"dayNumber": 7, "passageRef": "2 Corinthians 5:17-19", "theme": "Ministry of reconciliation", "prompt": "Looking back, what has begun to loosen in your heart this week?"},
    ],
    "marriage-14": [
        {"dayNumber": 1, "passageRef": "Genesis 2:24", "theme": "Two become one", "prompt": "What does 'one flesh' mean to you in this season of marriage?"},
        {"dayNumber": 2, "passageRef": "1 Corinthians 13:4-7", "theme": "Love is patient", "prompt": "Which quality of love does your marriage most need more of this week?"},
        {"dayNumber": 3, "passageRef": "Ephesians 4:2-3", "theme": "Bearing with each other", "prompt": "Where could you choose patience over being right today?"},
        {"dayNumber": 4, "passageRef": "Ephesians 4:26-27", "theme": "Don't let the sun go down on anger", "prompt": "Is there a lingering conflict you need to bring into the light together?"},
        {"dayNumber": 5, "passageRef": "Philippians 2:3-4", "theme": "Considering each other", "prompt": "What's one need of your spouse you could put ahead of your own today?"},
        {"dayNumber": 6, "passageRef": "Proverbs 15:1", "theme": "A gentle answer", "prompt": "Where could a softer tone change a recurring tension?"},
        {"dayNumber": 7, "passageRef": "Song of Songs 8:6-7", "theme": "Love that lasts", "prompt": "What first drew you to your spouse? Tell them today."},
        {"dayNumber": 8, "passageRef": "Colossians 3:12-14", "theme": "Clothed in compassion", "prompt": "Which 'garment' — kindness, humility, patience — could you put on for your spouse?"},
        {"dayNumber": 9, "passageRef": "Ecclesiastes 4:9-12", "theme": "A cord of three strands", "prompt": "How is God the 'third strand' in your marriage? How could you invite Him in more?"},
        {"dayNumber": 10, "passageRef": "1 Peter 4:8", "theme": "Love covers", "prompt": "What small offense could you simply let love cover today?"},
        {"dayNumber": 11, "passageRef": "James 1:19", "theme": "Quick to listen", "prompt": "How well are you listening to your spouse lately? What might they wish you heard?"},
        {"dayNumber": 12, "passageRef": "Romans 12:10", "theme": "Honor one another", "prompt": "How could you honor your spouse — privately and in front of others — this week?"},
        {"dayNumber": 13, "passageRef": "Ephesians 5:25-33", "theme": "Sacrificial love", "prompt": "What would sacrificial, self-giving love look like for you right now?"},
        {"dayNumber": 14, "passageRef": "Joshua 24:15", "theme": "As for us, we will serve the Lord", "prompt": "Looking back over two weeks, what's one commitment you want to make together?"},
    ],
    "gratitude-7": [
        {"dayNumber": 1, "passageRef": "Psalm 100", "theme": "Enter with thanksgiving", "prompt": "What's one thing you're thankful for this morning?"},
        {"dayNumber": 2, "passageRef": "1 Thessalonians 5:16-18", "theme": "Give thanks in all", "prompt": "Can you thank God inside a hard circumstance today?"},
        {"dayNumber": 3, "passageRef": "Psalm 103:1-5", "theme": "Forget not His benefits", "prompt": "List benefits from God you tend to forget."},
        {"dayNumber": 4, "passageRef": "Colossians 3:15-17", "theme": "Thankful hearts", "prompt": "Who could you thank today, out loud?"},
        {"dayNumber": 5, "passageRef": "Luke 17:11-19", "theme": "The one who returned", "prompt": "What good thing have you received but not yet thanked God for?"},
        {"dayNumber": 6, "passageRef": "Philippians 4:11-13", "theme": "Contentment", "prompt": "Where do you sense God growing contentment in you?"},
        {"dayNumber": 7, "passageRef": "Psalm 136:1", "theme": "His love endures", "prompt": "Write a short psalm of thanks in your own words."},
    ],
    "hope-10": [
        {"dayNumber": 1, "passageRef": "Romans 15:13", "theme": "The God of hope", "prompt": "Where do you most need to be filled with hope right now?"},
        {"dayNumber": 2, "passageRef": "Jeremiah 29:11", "theme": "Plans to give you hope", "prompt": "What future are you afraid of? How might God be holding it?"},
        {"dayNumber": 3, "passageRef": "Hebrews 6:19", "theme": "An anchor for the soul", "prompt": "What is your hope anchored to when everything feels unsteady?"},
        {"dayNumber": 4, "passageRef": "Romans 5:3-5", "theme": "Suffering produces hope", "prompt": "How have past hardships grown perseverance or character in you?"},
        {"dayNumber": 5, "passageRef": "Lamentations 3:21-23", "theme": "New every morning", "prompt": "What mercy can you look for fresh tomorrow morning?"},
        {"dayNumber": 6, "passageRef": "Isaiah 40:28-31", "theme": "Renewed strength", "prompt": "Where are you weary and in need of renewed strength today?"},
        {"dayNumber": 7, "passageRef": "Psalm 42:11", "theme": "Hope in God", "prompt": "What would you say to your own downcast soul right now?"},
        {"dayNumber": 8, "passageRef": "1 Peter 1:3-6", "theme": "A living hope", "prompt": "How does the resurrection give you a 'living' — not wishful — hope?"},
        {"dayNumber": 9, "passageRef": "Psalm 130:5-7", "theme": "Waiting in hope", "prompt": "What are you waiting on God for? How can you wait with hope, not just patience?"},
        {"dayNumber": 10, "passageRef": "Romans 8:24-25", "theme": "Hope we don't yet see", "prompt": "Looking back over ten days, where has your hope grown sturdier?"},
    ],
}
