<html>
<head>

</head>
<body>


<p class="p2"><span class="s3"><hr></span></p>
<p class="p2"><span class="s3"><h1><b>Atmeex Cloud Integration for Home Assistant</b></h1></span></p>





<p class="p1"><span class="s1"><h2><b>Overview</b></h2></span></p>
<p class="p2"><br></p>
<p class="p3"><span class="s2"><b>Atmeex Cloud</b></span> is a custom integration for <a href="https://www.home-assistant.io/">Home Assistant</a><span class="s3"><img src="file:///Attachment.tiff" alt="Attachment.tiff"></span> that connects your Atmeex (AirNanny) ventilation devices to the Home Assistant ecosystem.</p>
<p class="p3">It uses the official Atmeex Cloud REST API (<span class="s4">https://api.iot.atmeex.com</span>) to provide reliable control and monitoring of your brizers directly from Home Assistant dashboards and automations.</p>
<p class="p2"><br></p>
<blockquote style="margin: 0.0px 0.0px 0.0px 15.0px; font: 14.0px '.AppleSystemUIFont'; color: #0e0e0e">🧩 Originally based on the open-source integration developed by <span class="s2"><b>[<span class="s4">https://github.com/anpavlov</span>);]</b></span>, and extensively rewritten and expanded by <span class="s2"><b>Sergei Polunovskii</b></span> to support modern Home Assistant releases and the current Atmeex API.</blockquote>
<p class="p1"><span class="s1"><hr></span></p>
<p class="p1"><span class="s1"><h2><b>Features</b></h2></span></p>
<p class="p1"><span class="s1"><ul><li>
<p class="p1">Auto-discovery of all devices linked to your Atmeex Cloud account.</p>
</li><li>
<p class="p1">Power on/off control.</p>
</li><li>
<p class="p1">Fan speed control (1–7).</p>
</li><li>
<p class="p1">Operation modes: ventilation, recirculation, mixed, and fresh-air intake.</p>
</li><li>
<p class="p1">Target temperature control (°C).</p>
</li><li>
<p class="p1">Optional humidifier control (if supported by the device).</p>
</li><li>
<p class="p1">Real-time sensors for temperature and humidity.</p>
</li><li>
<p class="p1">Online/offline status displayed directly on the climate card.</p>
</li><li>
<p class="p1">Clean asynchronous I/O using Home Assistant’s shared <span class="s1">aiohttp</span> client session.</p>
</li></ul></span></p>
<p class="p1"><span class="s1"><hr></span></p>
<p class="p1"><span class="s1"><h2><b>Installation</b></h2></span></p>
<p class="p2"><br></p>
<p class="p1"><span class="s1"><h3><b>Option 1 — via HACS (recommended)</b></h3></span></p>
<p class="p1"><span class="s1"><ol start="1"><li>
<p class="p1"><span class="s1">Open </span><b>HACS → Integrations → Custom repositories</b><span class="s1">.</span></p>
</li><li>
<p class="p1">Add this repository:</p>
</li></ol></span></p>


<pre><code>https://github.com/pols1/atmeex_hacs</code></pre>


<p class="p1"><span class="s1"><ol start="2"><li>
<p class="p1">Choose <span class="s1"><b>Integration</b></span> as the repository type.</p>
</li><li>
<p class="p1">Find <span class="s1"><b>Atmeex Cloud</b></span> in HACS and click <span class="s1"><b>Install</b></span>.</p>
</li><li>
<p class="p1">Restart Home Assistant.</p>
</li></ol></span></p>
<p class="p2"><br></p>
<p class="p1"><span class="s1"><h3><b>Option 2 — manual installation</b></h3></span></p>
<p class="p1"><span class="s1"><ol start="1"><li>
<p class="p1">Copy the folder:</p>
</li></ol></span></p>


<pre><code>custom_components/atmeex_cloud</code></pre>


<p class="p1"><span class="s1"><ol start="1"><li>
<p class="p1">into your Home Assistant configuration directory:</p>
</li></ol></span></p>


<pre><code>/config/custom_components/</code></pre>


<p class="p1"><span class="s1"><ol start="1"><li>
<p class="p1"><br></p>
</li><li>
<p class="p1">Restart Home Assistant.</p>
</li></ol></span></p>
<p class="p1"><span class="s1"><hr></span></p>
<p class="p1"><span class="s1"><h2><b>Configuration</b></h2></span></p>
<p class="p1"><span class="s1"><ol start="1"><li>
<p class="p1"><span class="s1">Go to </span><b>Settings → Devices &amp; Services → Add Integration</b><span class="s1">.</span></p>
</li><li>
<p class="p1">Search for <span class="s1"><b>Atmeex Cloud</b></span>.</p>
</li><li>
<p class="p1">Enter your <span class="s1"><b>Atmeex account credentials</b></span> (email and password).</p>
</li><li>
<p class="p1">After successful login, all connected devices will appear automatically.</p>
</li></ol></span></p>
<p class="p2"><br></p>
<p class="p3">The integration uses an internal update coordinator with a 30-second polling interval.</p>
<p class="p1"><span class="s1"><hr></span></p>
<p class="p1"><span class="s1"><h2><b>Entities</b></h2></span></p>



Entity Type | Example | Description
-- | -- | --
climate | climate.brizer_bedroom | Main entity: on/off, fan, temperature, mode, humidifier
sensor | sensor.brizer_bedroom_temperature | Current room temperature
sensor | sensor.brizer_bedroom_humidity | Current humidity
binary_sensor | binary_sensor.brizer_bedroom_online | Online/offline status




<p class="p1">You can check detailed logs in:</p>
<p class="p2"><b>Settings → System → Logs → custom_components.atmeex_cloud</b><b></b></p>
<p class="p3"><span class="s1"><hr></span></p>
<p class="p3"><span class="s1"><h2><b>Development</b></h2></span></p>
<p class="p4"><br></p>
<p class="p3"><span class="s1"><h3><b>Local setup</b></h3></span></p>


<pre><code>git clone https://github.com/pols1/atmeex_hacs.git
cd atmeex_hacs</code></pre>


<p class="p1">All requests use Home Assistant’s shared async session (<span class="s1">async_get_clientsession(hass)</span>), ensuring clean resource management and no unclosed sessions.</p>
<p class="p2"><br></p>
<p class="p3"><span class="s2"><h3><b>Releasing a new version</b></h3></span></p>
<p class="p3"><span class="s2"><ol start="1"><li>
<p class="p1">Update the <span class="s1">"version"</span> field in <span class="s1">manifest.json</span>.</p>
</li><li>
<p class="p1">Commit and push your changes.</p>
</li><li>
<p class="p1">Tag the new release:</p>
</li></ol></span></p>


<pre><code>git tag -a v0.3.0 -m &quot;Release 0.3.0&quot;
git push --tags</code></pre>


<p class="p1"><span class="s1"><ol start="3"><li>
<p class="p1"><br></p>
</li><li>
<p class="p1">Create a GitHub Release (optionally auto-generate release notes).</p>
</li></ol></span></p>
<p class="p1"><span class="s1"><hr></span></p>
<p class="p1"><span class="s1"><h2><b>Credits</b></h2></span></p>
<p class="p1"><span class="s1"><ul><li>
<p class="p1">🧠 <span class="s1"><b>Development:</b></span> <a href="https://github.com/pols1">Sergei Polunovskii</a><span class="s2"><img src="file:///Attachment.tiff" alt="Attachment.tiff"></span></p>
</li><li>
<p class="p1"><span class="s1">⚙️ </span><b>Original base integration:</b><span class="s1"> [@&lt;PRIVATE_NAME&gt;]</span></p>
</li><li>
<p class="p1">🌐 <span class="s1"><b>API &amp; platform:</b></span> <a href="https://api.iot.atmeex.com">Atmeex / AirNanny Cloud</a><span class="s2"><img src="file:///Attachment.tiff" alt="Attachment.tiff"></span></p>
</li><li>
<p class="p1">🧩 <span class="s1"><b>Framework:</b></span> <a href="https://www.home-assistant.io">Home Assistant</a><span class="s2"><img src="file:///Attachment.tiff" alt="Attachment.tiff"></span></p>
</li></ul></span></p>
<p class="p1"><span class="s1"><hr></span></p>
<p class="p1"><span class="s1"><h2><b>License</b></h2></span></p>
<p class="p2"><br></p>
<p class="p3">Distributed under the <a href="LICENSE">MIT License</a><span class="s2"><img src="file:///Attachment.tiff" alt="Attachment.tiff"></span>.</p>
<p class="p3">See the LICENSE file for more details.</p>
<p class="p1"><span class="s1"><hr></span></p>
<p class="p3">Хочешь, я сделаю вторую половину README на русском (в секции <span class="s3">&lt;details&gt;</span>), чтобы HACS автоматически показывал и английскую, и русскую версию? Это улучшит восприятие пользователями в СНГ.</p>

</body>
</html>Отлично — вот обновлённый, чисто оформленный английский вариант README.md, в котором я добавил упоминание об исходном разработчике, на основе чьей интеграции ты построил текущую версию.
(я написал универсально, если у тебя есть конкретный ник — можно подставить его в строке “Originally based on work by …”).

⸻

Atmeex Cloud Integration for Home Assistant

Overview

Atmeex Cloud is a custom integration for [Home Assistant](https://www.home-assistant.io/)￼ that connects your Atmeex (AirNanny) ventilation devices to the Home Assistant ecosystem.
It uses the official Atmeex Cloud REST API (https://api.iot.atmeex.com) to provide reliable control and monitoring of your brizers directly from Home Assistant dashboards and automations.

🧩 Originally based on the open-source integration developed by [@<PRIVATE_NAME>], and extensively rewritten and expanded by Sergei Polunovskii to support modern Home Assistant releases and the current Atmeex API.

⸻

Features
	•	Auto-discovery of all devices linked to your Atmeex Cloud account.
	•	Power on/off control.
	•	Fan speed control (1–7).
	•	Operation modes: ventilation, recirculation, mixed, and fresh-air intake.
	•	Target temperature control (°C).
	•	Optional humidifier control (if supported by the device).
	•	Real-time sensors for temperature and humidity.
	•	Online/offline status displayed directly on the climate card.
	•	Clean asynchronous I/O using Home Assistant’s shared aiohttp client session.

⸻

Installation

Option 1 — via HACS (recommended)
	1.	Open HACS → Integrations → Custom repositories.
	2.	Add this repository:

https://github.com/pols1/atmeex_hacs

Choose Integration as the repository type.

	3.	Find Atmeex Cloud in HACS and click Install.
	4.	Restart Home Assistant.

Option 2 — manual installation
	1.	Copy the folder:

custom_components/atmeex_cloud

into your Home Assistant configuration directory:

/config/custom_components/


	2.	Restart Home Assistant.

⸻

Configuration
	1.	Go to Settings → Devices & Services → Add Integration.
	2.	Search for Atmeex Cloud.
	3.	Enter your Atmeex account credentials (email and password).
	4.	After successful login, all connected devices will appear automatically.

The integration uses an internal update coordinator with a 30-second polling interval.

⸻

Entities

Entity Type	Example	Description
climate	climate.brizer_bedroom	Main entity: on/off, fan, temperature, mode, humidifier
sensor	sensor.brizer_bedroom_temperature	Current room temperature
sensor	sensor.brizer_bedroom_humidity	Current humidity
binary_sensor	binary_sensor.brizer_bedroom_online	Online/offline status


⸻

Humidifier Control

If your device supports a humidifier, a humidity slider will appear under the climate card.
It has four fixed stages, automatically snapping to the nearest level:

Slider position	Mode
0%	Off
33%	Stage 1
66%	Stage 2
100%	Stage 3

Intermediate values (e.g. 25%, 80%) are automatically rounded to the nearest valid stage.

⸻

Troubleshooting

Problem	Cause	Fix
Integration fails to load	Old or corrupted files	Reinstall from HACS
Auth failed during setup	Wrong credentials	Verify your Atmeex Cloud email and password
Temperature shows -100°C	API didn’t return room temperature	Wait for the next update or restart Home Assistant
Second brizer missing	API returned null for device condition	Fixed in recent releases

You can check detailed logs in:
Settings → System → Logs → custom_components.atmeex_cloud

⸻

Development

Local setup

git clone https://github.com/pols1/atmeex_hacs.git
cd atmeex_hacs

All requests use Home Assistant’s shared async session (async_get_clientsession(hass)), ensuring clean resource management and no unclosed sessions.

Releasing a new version
	1.	Update the "version" field in manifest.json.
	2.	Commit and push your changes.
	3.	Tag the new release:

git tag -a v0.3.0 -m "Release 0.3.0"
git push --tags


	4.	Create a GitHub Release (optionally auto-generate release notes).

⸻

Credits
	•	🧠 Development: [Sergei Polunovskii](https://github.com/pols1)￼
	•	⚙️ Original base integration: [(https://github.com/anpavlov)]
	•	🌐 API & platform: [Atmeex / AirNanny Cloud](https://api.iot.atmeex.com/)￼
	•	🧩 Framework: [Home Assistant](https://www.home-assistant.io/)￼

⸻

License

Distributed under the [MIT License](https://github.com/pols1/atmeex_hacs/releases/edit/LICENSE)￼.
See the LICENSE file for more details.

⸻
