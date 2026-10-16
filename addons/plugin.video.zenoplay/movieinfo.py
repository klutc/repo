import xbmcgui
from labels import movie_label, movie_year

class MovieInfo(xbmcgui.WindowXMLDialog):
    def __init__(self, *args, **kwargs):
        self.movie = kwargs.pop('movie')
        self.allow_sources = kwargs.pop('allow_sources', True)
        self.action_label = kwargs.pop('action_label', 'Пусни филма')
        self.proceed = False

    def onInit(self):
        data = dict(self.movie,year=movie_year(self.movie))
        self.getControl(101).setImage(data.get('icon',''))
        self.getControl(102).setLabel(movie_label(data.get('name') or data.get('title',''),data.get('year',0)))
        self.getControl(103).setLabel('Година: ' + (str(data['year']) if data.get('year') else '—'))
        self.getControl(104).setLabel('Жанр: ' + (' / '.join(data.get('genres',[])) or '—'))
        self.getControl(106).setLabel('Държава: ' + (' / '.join(data.get('countries',[])) or '—'))
        actors = data.get('actors') or []
        actors = [str(actor.get('name') or '') if isinstance(actor, dict) else str(actor) for actor in actors]
        actors = [actor for actor in actors if actor]
        self.getControl(107).setText('Актьори: ' + (', '.join(actors) or '—'))
        self.getControl(105).setText(data.get('plot') or 'Няма налично резюме.')
        self.getControl(10).setLabel(self.action_label if self.allow_sources else 'Затвори')

    def onClick(self, controlId):
        if controlId in (10,11):
            self.proceed = controlId == 10 and self.allow_sources
            self.close()

    def onAction(self, action):
        if action.getId() in (9,10,92):
            self.close()
