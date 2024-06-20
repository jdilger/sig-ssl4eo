import collections
import argparse
from pathlib import Path
from types import SimpleNamespace
import csv
import io
import logging
from dataclasses import dataclass
from typing import Literal

import apache_beam as beam
from apache_beam.options.pipeline_options import PipelineOptions
from apache_beam.io import ReadFromCsv, WriteToText

from fao_models.common import load_yml

# from _types import Config

logging.basicConfig(format="%(asctime)s - %(message)s", level=logging.INFO)
TMP = "/Users/johndilger/Documents/projects/SSL4EO-S12/fao_models/TMP"
BANDS = [
    "B1",
    "B2",
    "B3",
    "B4",
    "B5",
    "B6",
    "B7",
    "B8",
    "B8A",
    "B9",
    "B10",
    "B11",
    "B12",
]
CROPS = [44, 264, 264, 264, 132, 132, 132, 264, 132, 44, 44, 132, 132]
PROJECT = "pc530-fao-fra-rss"


@dataclass
class Config:
    imgs_training: str
    labels_training: str
    imgs_testing: str
    labels_testing: str

    arch: Literal["vit_small"]
    model_root: str | Path
    avgpool_patchtokens: bool
    patch_size: int
    n_last_blocks: int
    lr: float
    batch_size: int
    checkpoints_dir: str | Path
    resume: bool
    epochs: int
    num_workers: int
    seed: int
    random_subset_frac: float
    model_head_root: str | Path
    model_name: str
    checkpoint_key: str = "teacher"


# https://github.com/kubeflow/examples/blob/master/LICENSE
class DictToCSVString(beam.DoFn):
    """Convert incoming dict to a CSV string.

    This DoFn converts a Python dict into
    a CSV string.

    Args:
      fieldnames: A list of strings representing keys of a dict.
    """

    def __init__(self, fieldnames):
        # super(DictToCSVString, self).__init__()

        self.fieldnames = fieldnames

    def process(self, element, *_args, **_kwargs) -> collections.abc.Iterator[str]:
        """Convert a Python dict instance into CSV string.

        This routine uses the Python CSV DictReader to
        robustly convert an input dict to a comma-separated
        CSV string. This also handles appropriate escaping of
        characters like the delimiter ",". The dict values
        must be serializable into a string.

        Args:
          element: A dict mapping string keys to string values.
            {
              "key1": "STRING",
              "key2": "STRING"
            }

        Yields:
          A string representing the row in CSV format.
        """
        import io
        import csv

        fieldnames = self.fieldnames
        filtered_element = {
            key: value for (key, value) in element.items() if key in fieldnames
        }
        with io.StringIO() as stream:
            writer = csv.DictWriter(stream, fieldnames)
            writer.writerow(filtered_element)
            csv_string = stream.getvalue().strip("\r\n")

        yield csv_string


class ComputeWordLengthFn(beam.DoFn):
    def process(self, element):
        return [len(element)]


import ee
import google.auth
from fao_models.models._models import get_model
from fao_models.models.dino.utils import restart_from_checkpoint
import torch
from fao_models.datasets.ssl4eo_dataset import SSL4EO
import os


class Predict(beam.DoFn):
    def __init__(self, config_path):
        from fao_models.common import load_yml
        from fao_models._types import Config

        self._config = Config(**load_yml(config_path))
        logging.info(f"config :{self._config.__dict__}")
        # super().__init__()

    def setup(self):
        self.load_model()
        # return super().setup()

    def load_model(self):
        """load model"""
        from fao_models.models._models import get_model
        from fao_models.models.dino.utils import restart_from_checkpoint
        import os

        c = self._config
        self.model, self.linear_classifier = get_model(**c.__dict__)
        restart_from_checkpoint(
            os.path.join(c.model_head_root),
            state_dict=self.linear_classifier,
        )

    def process(self, element):
        import torch
        from fao_models.datasets.ssl4eo_dataset import SSL4EO

        if element["img_root"] == "RuntimeError":
            element["prob_label"] = 0
            element["pred_label"] = 0
            yield element

        else:
            dataset = SSL4EO(
                root=element["img_root"].parent,
                mode="s2c",
                normalize=False,  # todo add normalized to self._config.
            )

            image = dataset[0]
            image = torch.unsqueeze(torch.tensor(image), 0).type(torch.float32)

            self.linear_classifier.eval()
            with torch.no_grad():
                intermediate_output = self.model.get_intermediate_layers(
                    image, self._config.n_last_blocks
                )
                output = torch.cat([x[:, 0] for x in intermediate_output], dim=-1)

            output = self.linear_classifier(output)
            element["prob_label"] = output.detach().cpu().item()
            element["pred_label"] = round(element["prob_label"])
            yield element


class GetImagery(beam.DoFn):
    def __init__(self, dst):
        self.dst = dst
        self.PROJECT = PROJECT
        self.BANDS = BANDS
        self.CROPS = CROPS
        # super().__init__()

    def setup(self):
        import ee
        import google.auth

        credentials, _ = google.auth.default()
        ee.Initialize(
            credentials,
            project=self.PROJECT,
            opt_url="https://earthengine-highvolume.googleapis.com",
        )
        # return super().setup()

    def process(self, element):
        """download imagery"""
        from fao_models.download_data.download_wraper import single_patch
        from pathlib import Path
        import time
        from datetime import datetime

        st = time.time()
        try:

            sample = element
            print(f"start {sample.global_id}")
            coords = (sample.long, sample.lat)
            local_root = Path(self.dst)
            img_root = single_patch(
                coords,
                id=sample.global_id,
                dst=local_root / "imgs",
                year=2019,
                bands=self.BANDS,
                crop_dimensions=self.CROPS,
            )
            time_to_str = lambda t: datetime.fromtimestamp(t).strftime(
                "%Y-%m-%d %H:%M:%S,%f"
            )[:-3]
            et = time.time()
            # print(f"img {sample.global_id} took:{et-st}")
            # print(
            #     f"img {sample.global_id} start: {time_to_str(st)} end: {time_to_str(et)}"
            # )
            print(f"end {sample.global_id}")
            yield {
                "img_root": img_root,
                "long": sample.long,
                "lat": sample.lat,
                "id": sample.global_id,
            }
        except RuntimeError:
            logging.warning(f"no image found for sample: {sample.global_id}")
            # no image found
            yield {
                "img_root": "RuntimeError",
                "long": sample.long,
                "lat": sample.lat,
                "id": sample.global_id,
            }


def pipeline(beam_options, dotargs: SimpleNamespace):
    logging.info("Pipeline is starting.")
    import time

    st = time.time()
    if beam_options is not None:
        beam_options = PipelineOptions(**load_yml(beam_options))

    cols = ["id", "long", "lat", "prob_label", "pred_label"]
    options = PipelineOptions(
        runner="DirectRunner",  # or 'DirectRunner'
        direct_num_workers=16,
        direct_running_mode="multi_processing",
        max_num_workers=20,
    )
    # transforms.util.Reshuffle
    from apache_beam.options.pipeline_options import (
        DirectOptions,
    )  # .options.pipeline_options.DirectOptions()

    o = DirectOptions()
    with beam.Pipeline(options=options) as p:
        bdf = (
            p
            | "read input data" >> ReadFromCsv(dotargs.input, splittable=True)
            | "Reshuffle" >> beam.Reshuffle()
            | "download imagery"
            >> beam.ParDo(GetImagery(dst=TMP)).with_output_types(dict)
            | "predict"
            >> beam.ParDo(Predict(config_path=dotargs.model_config)).with_output_types(
                dict
            )
            | "to csv str" >> beam.ParDo(DictToCSVString(cols))
            | "write to csv" >> WriteToText(dotargs.output, header=",".join(cols))
        )
        # bdf =
    print(f"pipeline took {time.time()-st}")


def run():
    argparse.FileType()

    parser = argparse.ArgumentParser()
    parser.add_argument("--input", "-i", type=str, required=True)
    parser.add_argument("--output", "-o", type=str, required=True)
    parser.add_argument("--model-config", "-mc", type=str, required=True)
    group = parser.add_argument_group("pipeline-options")
    group.add_argument("--beam-config", "-bc", type=str)
    args = parser.parse_args()

    pipeline(beam_options=args.beam_config, dotargs=args)


if __name__ == "__main__":
    run()
