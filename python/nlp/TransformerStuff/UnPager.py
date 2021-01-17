from collections import defaultdict

from python.layouteagle.pathant.Converter import converter
from python.layouteagle.pathant.PathSpec import PathSpec


@converter("wordi.page.*", 'wordi.*')
class UnPager(PathSpec):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        pass

    def __call__(self, feature_meta, *args, **kwargs):
        whole_doc_id = None
        whole_annotation = []
        whole_meta = {}

        for wordi, meta in feature_meta:
            if whole_doc_id and meta["doc_id"]  != whole_doc_id:
                yield whole_annotation, whole_meta
                whole_annotation = []
                whole_meta = defaultdict(list)

            whole_annotation.append(wordi)
            self.reduce_meta_list_prop(['original_text', 'original_indices'], whole_meta, meta)
            whole_doc_id = meta["doc_id"]

    default_values = {
        str: "",
        list: [],
        dict: {}
    }

    def reduce_meta_list_prop(self, props, whole_meta, part_meta):
        for prop in props:
            if not prop in whole_meta:
                whole_meta[prop] = self.default_values[type(part_meta[prop])]
            whole_meta[prop] = whole_meta[prop] + part_meta[prop]
