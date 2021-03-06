import os

from python.layouteagle import config
from python.layouteagle.pathant.Converter import converter
from python.layouteagle.pathant.PathSpec import PathSpec
import pandas as pd

@converter("wordi.*", 'css.*')
class Wordi2Css(PathSpec):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        pass

    def write_css(self, selector, data, output):
        children = []
        attributes = []

        for key, value in data.items():
            if hasattr(value, 'items'):
                children.append((key, value))
            else:
                attributes.append((key, value))


        for key, value in children:
            self.write_css(selector + (key,), value, output)

    def window_overlap(self, i1, i2, j1, j2):
        if i1 >= j1 and i2 <= j2:
            return (i1,i2)
        else:
            return None

    def __call__(self, feature_meta, *args, **kwargs):
        for annotation, meta in feature_meta:
            tags, words = list(zip(*annotation))

            i_to_tag = {}
            for _i, _i2s in meta["_i_to_i2"].items():
                for _i2 in _i2s:
                    if _i not in i_to_tag or i_to_tag[_i] == "O":
                        if _i2 < len(tags):
                            i_to_tag[_i] = annotation[_i2]

            css = self.parse_to_css(i_to_tag, meta)

            nested_dict_list = []
            i_word = dict(meta['i_word'])
            for _i, _i2s in meta["_i_to_i2"].items():
                nested_dict_list.append(
                    {
                        '_i': _i,
                        'hex id': f""".z{hex(_i)[2:]}""",
                        '_i2': _i2s,
                        'tags': i_to_tag[_i][0] if _i in i_to_tag else "no _i in _i_to_tag",
                        #'__tags': [annotation[x] for x in _i2s],

                        'i_word': i_word[_i],

                        'text': i_to_tag[_i][1] if _i in i_to_tag else "no _i in _i_to_tag"}
                )
            df = pd.DataFrame(nested_dict_list).sort_values(by='_i')

            with open(
                    os.path.join(
                        config.hidden_folder + "log/",
                        meta['doc_id'].replace("/", "").replace(".", "") + ".txt")
                    , 'w') as f:
                df.to_string(f, index=False)

            yield css, meta

    def parse_to_css(self, css_obj, meta):
            return "\n".join([
f""".z{hex(i)[2:]} {{
    {meta["CSS"][annotation[0]]}
    }}
""" for i, annotation in css_obj.items()])
