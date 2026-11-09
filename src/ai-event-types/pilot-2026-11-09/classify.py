"""Pilot: AI-suggested ado:hasEventTypeConcept for 100 untyped Artsdata events.
Outputs:
  ai-event-types-pilot.ttl  - Turtle-star (RDF 1.2 annotation syntax) for a dedicated AI source graph
  ai-event-types-review.csv - review sheet for humans
"""
import csv, collections

RUN = "2026-11-09"
GRAPH = "http://kg.artsdata.ca/ai-event-type-classifier"

LABELS = {
 "MusicPerformance":"Concert","TheatrePerformance":"Theatre Performance",
 "MusicalTheatrePerformance":"Musical Theatre Performance","ComedyPerformance":"Comedy Performance",
 "DancePerformance":"Dance Performance","CircusPerformance":"Circus Performance",
 "TalkEvent":"Talk","WorkshopEvent":"Workshop","ScreeningEvent":"Screening",
 "AwardsEvent":"Awards Event","SocialEvent":"Social Event","ChildrensEvent":"Children's Event",
 "StorytellingPerformance":"Storytelling Performance","ExhibitionEvent":"Exhibition",
 "Competition":"Competition", None:"(no suggestion)",
}

# (id, name, venue, concept or None, confidence, rationale)
D = [
("K23-11751","Gala de l'Adisq 2026","Salle Wilfrid-Pelletier","AwardsEvent",.95,"Annual music industry awards gala"),
("K43-12873","House Teams Showcase","The Improv Centre","ComedyPerformance",.90,"Improv teams performing comedy"),
("K43-4048","Bee Gees Revisited","Port Theatre","MusicPerformance",.95,"Tribute band concert"),
("K43-9720","Black & Rural","Vernon and District PAC","TheatrePerformance",.65,"Solo stage show; could be storytelling"),
("K43-9760","Burnstick","R.E.M. Lee Theatre","MusicPerformance",.90,"Description refers to 'Burnstick's concerts'"),
("K23-11160","An Evening with Ta-Nehisi Coates","Chan Centre","TalkEvent",.85,"Author appearance"),
("K43-7728","500 Words","Flato Markham Theatre",None,.0,"No description; weekday morning slots suggest a school show"),
("K43-7729","500 Words","Flato Markham Theatre",None,.0,"No description; weekday morning slots suggest a school show"),
("K43-10473","TIFF: Sentimental Value","Imperial Theatre","ScreeningEvent",.95,"TIFF film title"),
("K43-3415","Séance d'information | Devenir bénévole","Bibl. Germaine-Guèvremont","TalkEvent",.60,"Info session; weak fit to any type"),
("K43-12367","Club 10-13 : Crée ton propre signet","Bibl. Germaine-Guèvremont","WorkshopEvent",.75,"Hands-on craft club for ages 10-13; ChildrensEvent also plausible"),
("K43-8148","An Arabian Adventure","Townshend Theatre",None,.0,"Name only; touring venues include schools"),
("K43-11898","Cœurs en cordes","Théâtre Capitol","MusicPerformance",.95,"Orchestra with conductor and violin soloist"),
("K43-12293","Tulua","Marigold Cultural Centre","MusicPerformance",.90,"Irish traditional band (other dates' descriptions)"),
("K43-12773","Triumph and Tribute","Fredericton Playhouse","MusicPerformance",.55,"No description; title and Remembrance week suggest a concert"),
("K43-13704","de Geneviève Dulude-De Celles","Salle Les-Frères-Lemaire","ScreeningEvent",.60,"Name is a filmmaker credit; title appears truncated"),
("K43-13463","Kaska Voices: An evening of storytelling","YAC Mainstage","StorytellingPerformance",.85,"Title says storytelling"),
("K23-10092","Allison Russell – In The House of Chaos Tour","Chan Centre","MusicPerformance",.95,"Singer-songwriter tour"),
("K43-8826","Ron James","Port Theatre","ComedyPerformance",.97,"Stand-up comedian"),
("K43-9761","Burnstick","Mount Elizabeth Theatre","MusicPerformance",.90,"Concert per description"),
("K43-10547","Acoustic Blues Reunion","Tidemark Theatre","MusicPerformance",.95,"Blues musicians concert"),
("K43-7730","500 Words","Flato Markham Theatre",None,.0,"No description; weekday morning slots suggest a school show"),
("K43-7731","500 Words","Flato Markham Theatre",None,.0,"No description; weekday morning slots suggest a school show"),
("K23-11891","Atelier photobroderie","Bibl. Notre-Dame-du-Mont-Carmel","WorkshopEvent",.90,"'Atelier' = workshop"),
("K43-10466","Ria Mae: Tour Two (Part Two)","Imperial Theatre","MusicPerformance",.90,"Singer tour"),
("K43-8776","Trent McClellan's Be Nice Tour","Théâtre Capitol","ComedyPerformance",.85,"Comedian tour"),
("K43-12133","Jonathan Mak - Debut Atlantic Classical Series","St. Andrew's United Church","MusicPerformance",.95,"Pianist recital"),
("K43-8151","An Arabian Adventure","St. Patrick's School",None,.0,"Name only; school venue"),
("K43-8372","Atelier 8 ans et plus | LEGO Spike","Bibl. Laure-Conan","WorkshopEvent",.90,"Robotics workshop for kids"),
("K43-10891","Compagnie de Fakto - C'est la vida !","La Caserne","DancePerformance",.75,"Fakto is a street-dance company"),
("K43-11295","TULUA - Irish Traditional","Osprey Arts Centre","MusicPerformance",.97,"Irish traditional band"),
("K43-11964","Signature 3: HeartStrings","Fredericton Playhouse","MusicPerformance",.90,"Symphony subscription concert"),
("K43-8338","Conférence | Élections américaines de mi-mandat","Bibl. Laure-Conan","TalkEvent",.95,"Lecture ('conférence')"),
("K43-8398","Atelier d'initiation à la lactofermentation","Bibl. Sylvain-Garneau","WorkshopEvent",.90,"Workshop"),
("K43-7772","Lisa Loeb","Partridge Hall","MusicPerformance",.95,"Double-bill concert with Joan Osborne"),
("K43-7840","Sophies Surprise 29th","Betty Speers Theatre","CircusPerformance",.70,"'Circus, comedy and chaos' (other date's description); Variety also plausible"),
("K43-13300","Robert Thomas and the Sessionmen In Concert","Fourth Stage","MusicPerformance",.97,"Concert; source already says schema:MusicEvent"),
("K43-13588","MONKS","Tarragon Theatre","TheatrePerformance",.80,"Tarragon theatre production"),
("K43-11820","Uncovered: Bee Gees & The Beach Boys","Royal Conservatory","MusicPerformance",.85,"Song concert by a musical-theatre company"),
("K43-12472","Holiday in Zürich","Centaur Theatre","TheatrePerformance",.85,"Centaur Theatre production"),
("K43-13360","Le Grenier – Les 7 Doigts","Espace Saint-Denis","CircusPerformance",.95,"7 Doigts circus creation"),
("K43-8986","Evil Dead The Musical","Martha Cohen Theatre","MusicalTheatrePerformance",.97,"Musical"),
("K43-11189","Scott Ward - Comedy, Hypnosis, Psychic Trickster","YAC Mainstage","ComedyPerformance",.70,"Comedy/hypnosis; Variety also plausible"),
("K43-11932","True Story!","The Improv Centre","ComedyPerformance",.90,"Improv comedy"),
("K43-13045","CRFF Blue Heron","Tidemark Theatre","ScreeningEvent",.65,"CRFF likely a film festival screening"),
("K43-8590","CRASH TEST DUMMIES","Vernon and District PAC","MusicPerformance",.95,"Band concert"),
("K43-8814","SPOTLIGHT: Birdy","Port Theatre","DancePerformance",.97,"Taiwanese contemporary dance"),
("K43-9762","Burnstick","Lester Centre of the Arts","MusicPerformance",.90,"Concert per description"),
("K43-11480","Cory Doctorow Talks Enshittification","Sid Williams Theatre","TalkEvent",.95,"Author talk"),
("K43-12337","Tout-petits contes pour les 1-36 mois","Bibl. Sylvain-Garneau","ChildrensEvent",.80,"Stories for toddlers; Storytelling also plausible"),
("K43-12458","Holiday in Zürich","Centaur Theatre","TheatrePerformance",.85,"Centaur Theatre production"),
("K43-13667","d'Agatha Christie","Salle Les-Frères-Lemaire","TheatrePerformance",.75,"Agatha Christie play; title truncated + HTML entity"),
("K23-12260","Rencontre avec les artistes de l'exposition","Centre culturel du Vieux-Aylmer","TalkEvent",.80,"Artist meet-and-talk at an exhibition"),
("K43-13268","Nightingales Wartime Tribute","Darke Hall","MusicPerformance",.75,"Wartime songs tribute"),
("K23-12105","Rencontre poétique avec Denise Desautels","UQTR","TalkEvent",.65,"Poet conversation; Spoken Word also plausible"),
("K23-12097","Soirée Bienvenue Chez Vous","Maison du citoyen","SocialEvent",.90,"Welcome evening for newcomers"),
("K43-12663","REDS Men's Hockey - Moncton vs UNB","Aitken Centre",None,.0,"Sports game; no fitting type, maybe exclude from Artsdata"),
("K43-9765","Ridge","Fredericton Playhouse","TheatrePerformance",.85,"Verbatim theatre with live music"),
("K23-11174","L'Angleterre géorgienne (1714-1837)","UdeM Laval","TalkEvent",.85,"Les belles heures lecture series"),
("K43-9272","Rebanks Family Fellowship Concert","Royal Conservatory","MusicPerformance",.95,"Concert"),
("K43-12329","Conférence | Malte et les croisades","Bibl. Yves-Thériault","TalkEvent",.95,"Lecture"),
("K43-7290","Come From Away","Roxy Theatre","MusicalTheatrePerformance",.97,"Musical"),
("K43-11152","U of T presents Jazz Hybrid Ensemble","Edward Johnson Building","MusicPerformance",.97,"Jazz ensemble concert"),
("K43-13589","MONKS","Tarragon Theatre","TheatrePerformance",.80,"Tarragon theatre production"),
("K43-13744","Par Agatha Christie","Salle Les-Frères-Lemaire","TheatrePerformance",.75,"Agatha Christie play; title truncated"),
("K43-5354","Rachelle Élie","Espace St-Denis Studio-Cabaret","ComedyPerformance",.95,"Humorist one-woman show"),
("K43-11221","Brahms, un requiem allemand","Grand Théâtre de Québec","MusicPerformance",.98,"OSQ choral-orchestral concert"),
("K43-12476","Holiday in Zürich","Centaur Theatre","TheatrePerformance",.85,"Centaur Theatre production"),
("K23-11948","Ma première Quart de finale #1","Cinquième salle, PdA","Competition",.80,"Ma première Place des Arts song competition"),
("K43-8987","Evil Dead The Musical","Martha Cohen Theatre","MusicalTheatrePerformance",.97,"Musical"),
("K43-9881","An Acoustic Evening With William Prince","Creekside Theatre","MusicPerformance",.95,"Singer-songwriter concert"),
("K43-12869","TriviaProv","The Improv Centre","ComedyPerformance",.85,"Improv comedy"),
("K43-8497","Frozen","Abbotsford Arts Centre","MusicalTheatrePerformance",.85,"Gallery 7 Theatre stage musical"),
("K43-12389","Jay Scott - Toutes les rues sont silencieuses","Centre des arts d'Edmundston","MusicPerformance",.85,"Singer tour; 08:00 start looks wrong"),
("K23-12234","Présentation des travaux – création numérique","Atelier Presse Papier","ExhibitionEvent",.50,"Presentation of artists' works; Talk also plausible"),
("K43-11907","SNB: HeartStrings","Imperial Theatre","MusicPerformance",.95,"Symphony NB concert"),
("K43-14105","Atelier 11-17 ans | Est-ce que l'IA a du talent?","Bibl. Philippe-Panneton","WorkshopEvent",.90,"Workshop"),
("K43-14136","Atelier 8-18 ans | Synthonisation","Bibl. Émile-Nelligan","WorkshopEvent",.90,"Workshop"),
("K43-6904","The Men of the Deeps @ 60","Théâtre Capitol","MusicPerformance",.95,"Miners' choir concert"),
("K43-11248","The Bakersfield Sound Tribute","Fredericton Playhouse","MusicPerformance",.95,"Country music tribute"),
("K43-8149","An Arabian Adventure","Sioux North High School",None,.0,"Name only; school venue"),
("K23-11828","Lancement festival Rebel Sound / Soirée bénéfice","Le Temps d'une Pinte","SocialEvent",.60,"Launch/fundraiser party; Concert possible"),
("K43-14104","Atelier 8 ans+ | Mission robots","Bibl. Laure-Conan","WorkshopEvent",.80,"Robotics games for kids"),
("K43-14150","Atelier 8-17 ans | BeatLab","Bibl. Germaine-Guèvremont","WorkshopEvent",.90,"Music-making workshop"),
("K43-6879","K-POP INFINITY","Théâtre Rialto","MusicPerformance",.85,"'Live concert experience'"),
("K43-11422","Yesterday Once More - The Carpenters Songbook","Aultsville Theatre","MusicPerformance",.95,"Tribute concert"),
("K23-11427","Conférence: Le grand repos","Bois Papineau","TalkEvent",.95,"Nature lecture"),
("K43-12284","La Famille Vélociraptor | Les Petits Explorateurs","Petit Théâtre du Vieux Noranda","ChildrensEvent",.75,"Kids' show series"),
("K43-7291","Come From Away","Roxy Theatre","MusicalTheatrePerformance",.97,"Musical"),
("K43-7773","Lisa Loeb","Regina Rosen Auditorium","MusicPerformance",.95,"Concert"),
("K43-7846","Sophies Surprise 29th","River Run Centre","CircusPerformance",.70,"'Circus, comedy and chaos'"),
("K43-8081","Trooper","Betty Speers Theatre","MusicPerformance",.97,"Rock band"),
("K43-13590","MONKS","Tarragon Theatre","TheatrePerformance",.80,"Tarragon theatre production"),
("K23-9018","Ivan Boivin-Flamand","Maison de la culture Francis-Brisson","MusicPerformance",.95,"Singer-songwriter guitarist"),
("K43-7865","Great Canadian Roadtrip 2.0","Meridian Theatres","MusicPerformance",.95,"Doc Walker country concert"),
("K43-8232","Maude Landry - Trop cool","Centre des arts Shenkman","ComedyPerformance",.95,"Humorist show"),
("K23-10600","Plateau double: Emmanuelle Boucher / Les Rats d'Swompe","Salle Jean-Despréz","MusicPerformance",.97,"Country / trad-rock double bill"),
("K43-11821","Uncovered: Bee Gees & The Beach Boys","Royal Conservatory","MusicPerformance",.85,"Song concert"),
("K43-12042","Katrine Sansregret","Espace St-Denis Studio-Cabaret","ComedyPerformance",.80,"Humorist; cabaret venue"),
("K43-12470","Holiday in Zürich","Centaur Theatre","TheatrePerformance",.85,"Centaur Theatre production"),
]
assert len(D) == 100 and len({d[0] for d in D}) == 100

def esc(s): return s.replace("\\","\\\\").replace('"','\\"')

ttl = [f"""# AI-suggested event types — pilot run {RUN}
# Load into named graph <{GRAPH}>; rank this dataset below every real source.
# ado:confidence is a PROPOSED term (not yet in the Artsdata ontology).
@prefix ado:    <http://kg.artsdata.ca/ontology/> .
@prefix adr:    <http://kg.artsdata.ca/resource/> .
@prefix prov:   <http://www.w3.org/ns/prov#> .
@prefix schema: <http://schema.org/> .
@prefix xsd:    <http://www.w3.org/2001/XMLSchema#> .
@prefix rdfs:   <http://www.w3.org/2000/01/rdf-schema#> .
@prefix void:   <http://rdfs.org/ns/void#> .

<{GRAPH}> a void:Dataset ;
  schema:name "AI event type classifier"@en ;
  schema:maintainer <https://culturecreates.com> .

<{GRAPH}#run-{RUN}> a prov:Activity ;
  prov:startedAtTime "{RUN}T11:45:00-05:00"^^xsd:dateTime ;
  prov:wasAssociatedWith <https://www.anthropic.com/claude#claude-opus-5-5> ;
  rdfs:comment "Prompt v0.1: classify against adr:ArtsdataEventTypes v4.0 using name, description, additionalType, organizer, venue." .
"""]
for i,n,v,c,conf,why in D:
    if not c: continue
    ttl.append(f"""adr:{i} ado:hasEventTypeConcept adr:{c} {{|
    prov:wasGeneratedBy <{GRAPH}#run-{RUN}> ;
    ado:confidence "{conf:.2f}"^^xsd:decimal ;
    rdfs:comment "{esc(why)}" |}} .""")
open("ai-event-types-pilot.ttl","w").write("\n".join(ttl)+"\n")

rows = sorted(D, key=lambda d: (d[3] is not None, d[4]))  # no-suggestion first, then lowest confidence
with open("ai-event-types-review.csv","w",newline="") as f:
    w = csv.writer(f)
    w.writerow(["artsdata_id","url","event_name","venue","suggested_type","suggested_uri","confidence","rationale","decision (accept/reject/fix)","corrected_type","reviewer"])
    for i,n,v,c,conf,why in rows:
        w.writerow([i,f"http://kg.artsdata.ca/resource/{i}",n,v,LABELS[c],f"http://kg.artsdata.ca/resource/{c}" if c else "",f"{conf:.2f}" if c else "",why,"","",""])

cnt = collections.Counter(LABELS[d[3]] for d in D)
bands = collections.Counter(("none" if not d[3] else ">=0.85" if d[4]>=.85 else "0.70-0.84" if d[4]>=.70 else "<0.70") for d in D)
print(cnt.most_common()); print(bands)
