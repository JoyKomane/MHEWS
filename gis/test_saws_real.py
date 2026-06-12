# Test the CAP parser against the real SAWS alert
import sys
sys.path.insert(0, '/home/claude/mhews')

from gis.cap_parser import parse_cap_xml

REAL_SAWS_CAP = """<?xml version="1.0" encoding="UTF-8"?>
<alert xmlns="urn:oasis:names:tc:emergency:cap:1.2">
<identifier>18da973d5514a0233d9568c5117e85392026.06.10.10.59.35</identifier>
<sender>SAWSMeteoFactorySystem</sender>
<sent>2026-06-10T10:59:35+02:00</sent>
<status>Actual</status>
<msgType>Update</msgType>
<scope>Restricted</scope>
<info>
<language>en-EN</language>
<category>Met</category>
<event>Weather Advisory</event>
<urgency>Future</urgency>
<severity>Unknown</severity>
<certainty>Unknown</certainty>
<onset>2026-06-12T00:00:00+02:00</onset>
<expires>2026-06-12T23:59:59+02:00</expires>
<senderName>SAWSWesternCapeRegionalOffice</senderName>
<headline>Weather Advisory</headline>
<description>The combination of very cold, wet and windy conditions may result in a wind chill factor thus temperatures may feel colder than the measured values. Loss of vulnerable livestock and crops can be expected. Risk of hypothermia in humans due to exposure to very cold conditions is possible.</description>
<instruction>The public and small stock farmers are advised to take the necessary precaution to ensure the safety and health of their animals during very cold, wet and windy days. Limit outdoor activities and keep warm.</instruction>
<web>https://www.weathersa.co.za</web>
<area>
<areaDesc>Witzenberg / Ceres</areaDesc>
<polygon>-32.22419,20.24084 -32.31085,20.25417 -32.30316,20.21603 -32.42112,20.13202 -32.39731,20.07964 -32.64374,20.14119 -32.68576,20.19172 -32.75267,20.18761 -32.80496,20.2999 -32.86408,20.35717 -32.91081,20.36388 -32.94006,20.4386 -33.03628,20.38375 -33.06389,20.27905 -33.12089,20.31849 -33.15934,20.30644 -33.14991,20.25125 -33.19328,20.08698 -33.23879,20.01377 -33.31678,19.97204 -33.3627,19.90847 -33.38099,19.82979 -33.36452,19.58069 -33.42644,19.53791 -33.48051,19.4053 -33.55743,19.39539 -33.56779,19.3672 -33.61909,19.37859 -33.59747,19.31666 -33.61387,19.28001 -33.55884,19.23947 -33.56199,19.1854 -33.59749,19.16939 -33.52987,19.09953 -33.33261,19.08669 -33.26745,19.05767 -33.23712,19.07798 -33.20014,19.05773 -33.17961,19.07996 -33.12766,19.07242 -33.09192,19.17299 -32.98404,19.15371 -32.86816,19.18615 -32.73682,19.17177 -32.73096,19.20864 -32.6046,19.1376 -32.57193,19.15917 -32.57464,19.32005 -32.61636,19.35693 -32.60666,19.39612 -32.63811,19.44127 -32.56544,19.48681 -32.67324,19.52825 -32.62946,19.60495 -32.47062,19.62185 -32.43878,19.65487 -32.46351,19.67974 -32.44236,19.73024 -32.42031,19.70739 -32.38552,19.73662 -32.41112,19.76413 -32.36072,19.8178 -32.37728,19.93749 -32.18652,20.15183 -32.18449,20.18095 -32.22749,20.16636 -32.22419,20.24084</polygon>
</area>
</info>
</alert>"""

print("Testing real SAWS CAP alert...")
print("-" * 50)

result = parse_cap_xml(REAL_SAWS_CAP)

if result:
    print("✅ Parser SUCCESS on real SAWS data!")
    print()
    for key, value in result.items():
        display = str(value)[:80] + '...' if len(str(value or '')) > 80 else str(value)
        print(f"  {key:25} = {display}")
else:
    print("❌ Parser FAILED")
