"""Seed data: the two tables from the challenge brief, copied as given."""

# Customers whose card delivery failed on Tuesday.
# birth_date is ISO (YYYY-MM-DD) so it compares cleanly; address_type is "home" | "work".
CUSTOMERS = [
    # (id, full_name, phone, birth_date, district, address_type)
    (1, "Ayşe Kaya", "0532 000 00 01", "1988-03-14", "Kadıköy", "home"),
    (2, "Mehmet Demir", "0532 000 00 02", "1975-11-02", "Kadıköy", "work"),
    (3, "Zeynep Arslan", "0532 000 00 03", "1993-06-27", "Kadıköy", "home"),
    (4, "Can Yıldız", "0532 000 00 04", "1981-01-09", "Ataşehir", "home"),
    (5, "Elif Şahin", "0532 000 00 05", "1990-08-30", "Ataşehir", "work"),
    (6, "Burak Çelik", "0532 000 00 06", "1969-12-18", "Şişli", "home"),
    (7, "Selin Aydın", "0532 000 00 07", "1999-04-05", "Şişli", "home"),
    (8, "Ali Öztürk", "0532 000 00 08", "1984-07-21", "Beşiktaş", "work"),
]

# This week's courier slots. Day labels stay Turkish because the agent speaks them as-is.
SLOTS = [
    # (id, district, day, start_time, end_time, capacity)
    (1, "Kadıköy", "Perşembe", "09:00", "13:00", 1),
    (2, "Kadıköy", "Cuma", "14:00", "18:00", 1),
    (3, "Ataşehir", "Perşembe", "14:00", "18:00", 2),
    (4, "Şişli", "Cuma", "09:00", "13:00", 2),
    (5, "Beşiktaş", "Perşembe", "09:00", "13:00", 1),
]
