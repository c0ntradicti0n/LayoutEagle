import glob
import json
import logging
import os
from pprint import pprint

import networkx as nx
import falcon
import wordninja
from regex import regex

from RestPublisher.Resource import Resource
from RestPublisher.RestPublisher import RestPublisher
from RestPublisher.react import react
from Topics.TopicMaker import TopicMaker
from layouteagle import config
from layouteagle.helpers.cache_tools import file_persistent_cached_generator, uri_with_cache
from layouteagle.helpers.nested_dict_tools import type_spec_iterable
from layouteagle.pathant.Converter import converter


@converter("wordi", "topics.dict")
class Topics(RestPublisher, react):
    def __init__(self,
                 *args,
                 **kwargs):
        super().__init__(*args, **kwargs, resource=Resource(
            title="Topics",
            type="graph",
            path="topics",
            route="topics",
            access={"fetch": True, "read": True, "upload": True, "correct": True, "delete": True}))

        self.topics = None

    wordi_regex = regex.compile(" *\d+:(.*)")

    """@file_persistent_cached_generator(
        config.cache + os.path.basename(__file__).replace('.py', '') +
        '.json',
        if_cache_then_finished=True,
        if_cached_then_forever=False)"""
    def __call__(self, documents):
        documents = list(documents)
        self.topic_maker = TopicMaker()

        # print(len(list(zip(documents))))
        html_paths_json_paths_txt_paths, metas = list(zip(*documents))

        wordi_paths = [meta["wordi_path"] for meta in metas]
        # print(wordi_paths)
        texts = []
        paths = []
        print("Topicizing documents")

        for i, wordi in enumerate(wordi_paths):
            o = os.getcwd()
            print(f"opening {wordi} {o}  {i+1} of {len(wordi_paths)}")
            try:
                with open(wordi, 'r', encoding='utf-8', errors='ignore')  as f:
                    firstlines = [f.readline() for i in range(1000)]

                    words = [Topics.wordi_regex.search(w).group(1) for w in firstlines if Topics.wordi_regex.search(w)]
                    words = [w for w in words if w]
                    if words:
                        text = wordninja.split("".join(words)[:1000].replace(" ", ""))
                        texts.append(text)
                        paths.append(wordi)
                        print (text[:3])
            except FileNotFoundError:
                logging.error(f"no {wordi}, was not created?")

        self.topics, text_ids = self.topic_maker(texts, paths)
        yield self.topics, text_ids

    @uri_with_cache
    def on_get(self, req, resp):  # get all
        pdfs = [file for file in glob.glob(config.test_dir + "*.pdf")]

        value, meta = list(zip(*list(self.ant("pdf", "topics.graph")([(pdf, {}) for pdf in pdfs]))))

        pprint(type_spec_iterable(value))

        return value[0]
