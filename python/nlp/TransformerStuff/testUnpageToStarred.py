from python.layouteagle.pathant.PathAnt import PathAnt
from python.nlp.TransformerStuff.ElmoDifference import ElmoDifference
from python.nlp.TransformerStuff.UnPager import UnPager

a = UnPager
b = ElmoDifference

ant = PathAnt()
ant.info("erase_and_star.png")
pipe = ant("wordi.page.difference", "wordi.difference")
vals = [2,3,4]
css_value, html_meta = list(
                    zip(
                        *list(
                            pipe
                            ([(val, {})
                              for val
                              in vals]))))