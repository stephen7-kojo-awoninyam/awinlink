"""Curated positions, disciplines and specializations for existing sports."""

SPORT_CATEGORIES = {
    "Football": ("Goalkeeper", "Defender", "Midfielder", "Forward"),
    "Basketball": ("Point Guard", "Shooting Guard", "Small Forward", "Power Forward", "Center"),
    "Volleyball": ("Setter", "Outside Hitter", "Opposite Hitter", "Middle Blocker", "Libero", "Defensive Specialist"),
    "Athletics": ("Sprints", "Middle Distance", "Long Distance", "Hurdles", "Relays", "Jumps", "Throws", "Combined Events", "Race Walking", "Road Running", "Cross Country"),
    "Cricket": ("Batter", "Fast Bowler", "Spin Bowler", "All-rounder", "Wicketkeeper"),
    "Rugby": ("Prop", "Hooker", "Lock", "Flanker", "Number Eight", "Scrum-half", "Fly-half", "Centre", "Wing", "Fullback"),
    "Swimming": ("Freestyle", "Backstroke", "Breaststroke", "Butterfly", "Individual Medley", "Open Water", "Relay"),
    "Boxing": ("Amateur Boxing", "Professional Boxing"),
    "MMA": ("Striking", "Wrestling", "Submission Grappling", "Mixed Martial Arts"),
    "Cycling": ("Road", "Track", "Mountain Bike", "BMX Racing", "BMX Freestyle", "Cyclo-cross", "Trials"),
    "Tennis": ("Singles", "Doubles", "Mixed Doubles", "Wheelchair Tennis"),
    "Golf": ("Stroke Play", "Match Play", "Long Drive"),
    "Baseball": ("Pitcher", "Catcher", "First Baseman", "Second Baseman", "Third Baseman", "Shortstop", "Left Fielder", "Center Fielder", "Right Fielder", "Designated Hitter"),
    "Hockey": ("Goalkeeper", "Defender", "Midfielder", "Forward", "Ice Hockey Goaltender", "Ice Hockey Defenseman", "Ice Hockey Center", "Ice Hockey Winger"),
    "Esports": ("MOBA", "First-person Shooter", "Battle Royale", "Real-time Strategy", "Fighting Games", "Sports Simulation", "Racing Simulation", "Card Games"),
    "Motorsports": ("Karting", "Single-seater Racing", "Touring Car Racing", "GT Racing", "Endurance Racing", "Rally", "Rallycross", "Motorcycle Racing", "Motocross", "Drag Racing"),
    "Chess": ("Classical", "Rapid", "Blitz", "Bullet", "Correspondence"),
    "Badminton": ("Singles", "Doubles", "Mixed Doubles"),
    "Handball": ("Goalkeeper", "Left Wing", "Right Wing", "Left Back", "Right Back", "Center Back", "Pivot"),
    "Table Tennis": ("Singles", "Doubles", "Mixed Doubles", "Para Table Tennis"),
}


def normalized_name(name):
    return " ".join(name.split()).casefold()


SPORT_ALIASES = {
    "soccer": "Football",
    "association football": "Football",
    "track and field": "Athletics",
    "mixed martial arts": "MMA",
    "e-sports": "Esports",
    "motor sports": "Motorsports",
    "table-tennis": "Table Tennis",
    "ping pong": "Table Tennis",
}
