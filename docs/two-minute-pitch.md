# EchoLang: screen-recorded competition pitch

**Target:** Just under 3 minutes. Record the app first, then add narration. Leave the app's spoken confirmation audible. Use short, visible cuts during the eight-question listing flow; keep the actual review, confirmation, and search result on screen.

Open [the HTML presentation](../presentation.html) beside the phone-sized app window at `http://127.0.0.1:5173`. Start with your title slide, use slides 2 and 3 for the idea and gap, and leave slide 4 visible during both app flows. Move to slide 5 for the technical flowchart and stack, then slide 6 for the closing. Use the left and right arrow keys to change slides.

| Time | Show in the screen recording | Say |
| --- | --- | --- |
| 0:00–0:08 | Show slide 1 with the EchoLang title and your details. | “I'm Dhruv Maheshwari, a fourth-year CSE student at PES University. This is EchoLang.” |
| 0:08–0:26 | Move to slide 2. Choose a language, then show the EchoLang home screen. | “Two streets away, someone can fix your broken fan. But if they have never filled in an online profile, a search may never find them. Local skill can be close and still invisible.” |
| 0:26–0:35 | Show slide 3. Tap **Offer a service**; show the large circle. | “This is EchoLang: a local directory you can build and search by speaking.” |
| 0:35–1:08 | Leave slide 4 beside the demo. Tap the circle. Show a real spoken provider answer, a visible cut through later questions, then the final review and Publish button. Put **Sample listing** on screen if the contact details are synthetic. | “A worker chooses a language and answers one question at a time: what do you repair, where do you work, and how can people call you? Gnani’s Prisma transcribes the answers. EchoLang reads back the completed entry. The worker can correct it, then chooses to publish.” |
| 1:08–1:56 | Keep slide 4 open. Tap **Find help**. Speak “Mujhe Udaipur mein fan repair chahiye.” Show the transcript, spoken confirmation, Yes, local result, and Call button. Pause narration while the app speaks. | “Now I ask for fan repair in Udaipur. Prisma captures my Hindi and English. Groq-hosted GPT-OSS 120B understands the service and place. Gnani’s Timbre speaks the request back so I can check it.” **[Let the app speak.]** “I confirm. EchoLang reads a matching local entry and gives me one clear next step: Call. If it heard the wrong service or town, I can change it.” |
| 1:56–2:26 | Show slide 5's flowchart and tech stack beside the phone demo. | “React records a short voice turn. Gnani Prisma transcribes it. GPT-OSS 120B on Groq extracts the service and place. FastAPI confirms and routes the request. A worker reviews a draft before SQLite stores it; a customer searches those entries. Gnani Timbre speaks each reply.” |
| 2:26–2:58 | Move to slide 6 and show the simple closing line: **Local help, one conversation away.** | “One voice creates the directory. Another voice searches it. This is a working demo, not proof of provider quality or completed jobs. Our next step is a pilot in one town: can workers create accurate entries, and can neighbours find and call them? A skilled neighbour should not be invisible because they never filled out a form.” |

## Recording checklist

- Use an actual app recording with Gnani speech recognition and synthesis. Keep the response audio audible for one confirmation.
- Use sample contact details in the public video. Mark the resulting entry **Sample listing** on screen. Do not call the sample number.
- If no matching entry is prepared, show the real empty state and change the narration to “EchoLang searches its local directory and tells me when no entry matches.”
- Show cuts plainly. Do not present separate sessions as one continuous interaction.
- The public post must name Gnani’s APIs, tag Gnani AI, include **#GnaniAI** and **#GreatIndianAIInternshipChallenge**, and be live before the final submission. The deadline is 10 November 2026 at 11:59 PM IST.

