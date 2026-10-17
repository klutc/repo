# -*- coding: utf-8 -*-
import sys

import xbmcaddon
import xbmcgui
import xbmcplugin

HANDLE = int(sys.argv[1])
ADDON_ID = 'plugin.video.klutc.movies'
ADDON = xbmcaddon.Addon(ADDON_ID)

SOURCES = [
    ('30001', 'plugin.video.filmizip', 'FilmiZip by Klutc'),
    ('30002', 'plugin.video.filmi9', 'Filmi9 by Klutc'),
    ('30003', 'plugin.video.zenoplay', 'ZenoPlay by Klutc'),
]


def main():
    xbmcplugin.setContent(HANDLE, 'videos')
    for string_id, addon_id, name in SOURCES:
        target = 'plugin://%s/' % addon_id
        item = xbmcgui.ListItem(label=ADDON.getLocalizedString(int(string_id)))
        icon = 'special://home/addons/%s/resources/icon.png' % addon_id
        item.setArt({'icon': icon, 'thumb': icon})
        item.setInfo('video', {'title': name, 'plot': ADDON.getLocalizedString(30004)})
        item.setProperty('IsPlayable', 'false')
        xbmcplugin.addDirectoryItem(HANDLE, target, item, isFolder=True)
    xbmcplugin.endOfDirectory(HANDLE, cacheToDisc=True)


if __name__ == '__main__':
    main()
