import sys
import os
import xbmcvfs
import xbmcaddon
import traceback
from urllib.parse import parse_qsl, urlencode, urlsplit
import requests
import xbmc
import xbmcgui
import xbmcplugin
import resolveurl
import native_resolver
import browser
import hosts
import imdb as imdb_lookup
from catalog import Catalog
from movieinfo import MovieInfo
from labels import movie_label, source_label, movie_year, episode_metadata
import subtitles as subtitle_loader
from parser import BASE, categories, listing, detail, player_url, embed

HANDLE = int(sys.argv[1])
ROOT = sys.argv[0]
APP_NAME = 'FilmiZip by Klutc'
ADDON = xbmcaddon.Addon()
ADDON_PATH = ADDON.getAddonInfo('path'~5öÚ$z{-®éÜj×‹	ÊJN‚ˆ][KœÙ]Z[YU\J	Ø\XØ][Û‹İ›™˜\K›\Yİ\›	ÊBˆ][KœÙ]ÛÛ[ÛÚİ\
˜[ÙJBˆ][KœÙ]\
Éİ[X‰Îˆ™Ù]
	ÚXÛÛ‰Ë	ÉÊK	ÜÜİ\‰Îˆ™Ù]
	ÚXÛÛ‰Ë	ÉÊ_JBˆ]OY]K™Ù]
	İ]IÊHÜˆ™Ù]
	Û˜[YIË	ÉÊBˆYˆ™Ù]
	Ù\\ÛÙIÊN]OIô%t/ô.4-ô/´-	ÊÜÉÙ\\ÛÙI×JÉÈ8 %	Êİ]Bˆš[Ú[™›Ê][KXİ
\\ÛÙWÛY]Y]J]K™Ù]
	Ù\\ÛÙIË	ÉÊKÜİ™Ù]
	İ\›	Ë	ÉÊJK˜[YO]]JJBˆ›ÙÜ™\ÜÈH›XÙİZK‘X[ÙÔ›ÙÜ™\ÜÊ
Bˆ›ÙÜ™\ÜË˜Ü™X]JTÓSQK	ô%ô,4`4-t-´-4,4/t-H4/t,4,tb´.ô,ô,4`4`t.´.4`t`ô,t`´.4`´`4.8 )‰ÊBˆN‚ˆ\™XİÜHHÜËœ]š›Ú[Š›Xİ™œË˜[œÛ]T]
›XØYÛ‹YÛŠ
K™Ù]YÛ’[™›Ê	Ü›Ùš[IÊJK	ÜİX]\ÉÊBˆ˜XÚÈHİX]\ÖÌHYˆ\Ú[œİ[˜ÙJİX]\Ë
\İ\JJH[™İX]\È[ÙHİX]\ÂˆØØ[HİX]WÛØY\‹™İÛ›ØY
šY[Ë˜XÚË\™XİÜK›ÙÜ™\ÜÏ]\]JBˆYˆØØ[‚ˆ][KœÙ]İX]\ÊÛØØ[JBˆ^Ù\^Ù\[Ûˆ\È\œ›Ü‚ˆ›XË›ÙÊ	Ñš[Z^š\İX]\Îˆ	È
ÈİŠ\œ›ÜŠK›XË“ÑÕĞT“’S‘ÊBˆ›XÙİZK‘X[ÙÊ
K››İYšXØ][ÛŠTÓSQK	ô(t`ô,t`´.4`´`4.4`´-H4/t-H4`t-H4-ô,4`4-t-4.4at,ˆ	È
ÈİŠ\œ›ÜŠK›XÙİZK““ÕQ’PĞUSÓ—ÕĞT“’S‘ÊBˆš[˜[N‚ˆ›ÙÜ™\ÜË˜ÛÜÙJ
Bˆ›XÙİZK•Ú[™İÊL
KœÙ]›Ü\J‘UT“—ÕT“Ô“ÔT•KÉİ\›	×JBˆ›XÜYÚ[‹œÙ]™\ÛÛ™Y\›
S‘KYK][JB‚œHXİ
\œÙWÜ\Û
Ş\Ë˜\™İ–Ì—K›İš\
	ÏÉÊJJB˜Xİ[ÛˆH™Ù]
	ØXİ[Û‰Ë	ÚÛYIÊBšYˆXİ[Ûˆ›İ[ˆ
	Ù]Z[	Ë	Ü^IÊN‚ˆ›XÙİZK•Ú[™İÊL
K˜ÛX\”›Ü\J‘UT“—ÕT“Ô“ÔT•JBN‚ˆYˆXİ[ÛˆOH	Ú[™›ÉÎ‚ˆ›XÜYÚ[‹œÙ]›Ü\JS‘K	Ñš[ZVš\Ø][ÙÉË	Ù˜[ÙIÊBˆYˆXİ[ÛˆOH	ÚÛYIÎ‚ˆY
	ô(´b´`4`t-t/t-IË	ÜÙX\˜Ú	ÊBˆY
	ô'ô/´`t.ô-t-4/t/ˆ4-4/´,t,4,´-t/t.	Ë	Øœ›İÜÙIËTÑJBˆ›Üˆ˜[YK\›[ˆØ]YÛÜšY\ÊÙ]
TÑJJN‚ˆY
˜[YK	Øœ›İÜÙIË\›
Bˆ[YˆXİ[ÛˆOH	Øœ›İÜÙIÎ‚ˆœ›İÜÙJÉİ\›	×JBˆ[YˆXİ[ÛˆOH	ÜÙX\˜Ú	Î‚ˆ]Y\HH›XÙİZK‘X[ÙÊ
Kš[œ]
	ô(´b´`4`t-t/t-H4/t,4a4.4.ô/4.4.ô.4`t-t`4.4,4.ÉÊBˆYˆ]Y\Kœİš\

N‚ˆœ›İÜÙJTÑH
È	Ú[™^œÉÈ
È\›[˜ÛÙJXİ
ÏIÜÙX\˜Ú	ËİX˜Xİ[ÛIÜÙX\˜Ú	ËİÜO\]Y\Kœİš\

JJJBˆ[YˆXİ[ÛˆOH	Ù]Z[	Î‚ˆÚİÊ
Bˆ[YˆXİ[ÛˆOH	Ú[™›ÉÎ‚ˆ[™›×ÙX[ÙÊØ][ÙÊ
K™™]Ú
Éİ\›	×JK™Ù]
	Û˜[YIË	ÉÊK[İ×ÜÛİ\˜Ù\ÏQ˜[ÙJBˆ[YˆXİ[ÛˆOH	Ü^IÎ‚ˆ^J
B™^Ù\^Ù\[Ûˆ\È\œ›Ü‚ˆ›XË›ÙÊ	Ñš[Z^š\ˆ	È
È˜XÙX˜XÚË™›Ü›X]Ù^Ê
K›XË“ÑÑT”“ÔŠBˆ›XÙİZK‘X[ÙÊ
K›ÚÊTÓSQKİŠ\œ›ÜŠJBˆYˆXİ[ÛˆOH	Ü^IÎ‚ˆ›XÜYÚ[‹œÙ]™\ÛÛ™Y\›
S‘K˜[ÙK›XÙİZK“\İ][J
JB™š[˜[N‚ˆYˆXİ[Ûˆ›İ[ˆ
	Ü^IË	Ú[™›ÉÊN‚ˆ›XÜYÚ[‹™[™Ù‘\™XİÜJS‘KİXØÙYYYQT‘PÕÔ–WÓÒÊBˆYˆSP“RSÈ[™›XË™Ù]ÚÚ[‘\Š
HOH	ÜÚÚ[‹˜ÛÛ™›Y[˜ÙIÎ‚ˆ›XË™^Xİ]XZ[[Š	ĞÛÛZ[™\‹”Ù]šY]Ó[ÙJL
IÊBˆYˆUU×ÔVWÕT“[™T‘PÕÔ–WÓÒÎ‚ˆ›XË™^Xİ]XZ[[Š	Ô^SYYXJ	È
ÈUU×ÔVWÕT“
È	ÊIÊB