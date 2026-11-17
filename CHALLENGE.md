# CHALLENGE: Freya (YC S25) FDE Pre-Test, "An AI-native bank"

Source: the challenge brief (Turkish screenshots), received 2026-11-17. The summary is in English;
the data tables are copied as given.

## Premise
Banks still run on branches, call centers, forms and approval queues, with a person and a wait
behind every task. AI changes that: a model can talk to customers, read documents and prepare
decisions. We work at a newly opened, AI-native bank that has **no call center**. A voice assistant
talks to customers, and our first job is to build it.

## The task
The bank sent its first credit cards by courier this week. On **Tuesday** the courier could not
reach **8 customers** because they were not at the address. The bank wants to **call these
customers and book a new delivery time within this week**. How to build it is up to us.

### Customers
| Customer | Phone | Date of birth | District | Delivery address |
|---|---|---|---|---|
| Ayşe Kaya | 0532 000 00 01 | 14.03.1988 | Kadıköy | Home (Ev) |
| Mehmet Demir | 0532 000 00 02 | 02.11.1975 | Kadıköy | Workplace (İş yeri) |
| Zeynep Arslan | 0532 000 00 03 | 27.06.1993 | Kadıköy | Home (Ev) |
| Can Yıldız | 0532 000 00 04 | 09.01.1981 | Ataşehir | Home (Ev) |
| Elif Şahin | 0532 000 00 05 | 30.08.1990 | Ataşehir | Workplace (İş yeri) |
| Burak Çelik | 0532 000 00 06 | 18.12.1969 | Şişli | Home (Ev) |
| Selin Aydın | 0532 000 00 07 | 05.04.1999 | Şişli | Home (Ev) |
| Ali Öztürk | 0532 000 00 08 | 21.07.1984 | Beşiktaş | Workplace (İş yeri) |

### This week's courier slots
| District | Day | Time window | Capacity |
|---|---|---|---|
| Kadıköy | Thursday (Perşembe) | 09:00-13:00 | 1 |
| Kadıköy | Friday (Cuma) | 14:00-18:00 | 1 |
| Ataşehir | Thursday (Perşembe) | 14:00-18:00 | 2 |
| Şişli | Friday (Cuma) | 09:00-13:00 | 2 |
| Beşiktaş | Thursday (Perşembe) | 09:00-13:00 | 1 |

### Rules and constraints given
- A card is handed over **only to the cardholder, after their ID has been seen**.
- "That's all we know. Add any missing rule yourself."
- The bank has **no system**. We write the service that holds the table data, and the assistant
  calls it during the conversation.
- A Freya account is free for **voice and LLM**. The cost of any other service is ours.
- **No screen or UI is required.**

## Process rules
- **2 hours of development**, screen recorded from start to finish (audio optional). Stop at 2 hours
  even if unfinished.
- The plan can change at any time, but **note the time** of each change.
- Any AI tool and any language are allowed. The Freya platform is optional; an account is available
  on request from the contact person.
- If something is unclear, decide yourself, carry on without waiting for a reply, and state the
  decision in the video.

## Deliverables (one message to the contact person)
1. Link to the 2-hour screen recording.
2. Link to the explanation video (at most 10 minutes, screen and voice) covering:
   - what we built, what we knowingly left out, and a short look at the code structure;
   - a **live voice trial** of the assistant;
   - how we measured that it works, and what we found;
   - what we would add or change before running this at a real bank;
   - the times we changed direction, and why.
3. Code link (GitHub or zip).
4. AI chat logs.

Unfinished is fine: they want to see what we did and why.

## What the data implies
- **Not enough slots:** 8 customers, 7 slots. Kadıköy has 3 customers but only 2 slots, so at least
  one Kadıköy customer cannot be served this week.
- **One window per district:** Ataşehir (Thu afternoon), Şişli (Fri morning) and Beşiktaş (Thu
  morning, 1 slot) each offer a single window, so there is no alternative if it doesn't suit.
- **Date of birth is given**, which is a natural identity check on the call.
- **Only the address type (home/work) is given, not the address.** A change of address could move a
  customer into another district's slots, and is a known fraud vector.
- Workplace deliveries still need the cardholder there in person with ID.

## Rules we must add ourselves (to decide in the briefing)
- Identity check on the call; what happens if someone else answers.
- What happens when no slot fits (next week, waitlist, callback?).
- Address changes: allowed? across districts? extra checks?
- Can someone else receive the card (spouse, colleague)? The given rule implies no.
- No answer, voicemail, "call me later": retry policy.
- Off-topic questions and escalation, given there is no call center.
- Two calls competing for the last slot (booking must be atomic).
- Recording each call's outcome for the bank.
