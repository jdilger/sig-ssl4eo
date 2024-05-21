import collections
from pathlib import PosixPath
import apache_beam as beam
from apache_beam.options.pipeline_options import PipelineOptions
from apache_beam.io import ReadFromCsv, WriteToCsv, WriteToText
from apache_beam.dataframe.io import read_csv, to_csv

P = "/Users/johndilger/Documents/projects/SSL4EO-S12/fao_models/data/match_dev.csv"
O = "/Users/johndilger/Documents/projects/SSL4EO-S12/fao_models/beamout.csv"
CONFIG = "/Users/johndilger/Documents/projects/SSL4EO-S12/fao_models_runs/test.yml"
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

import csv
import io
import apache_beam as beam


# https://github.com/kubeflow/examples/blob/master/LICENSE
class DictToCSVString(beam.DoFn):
    """Convert incoming dict to a CSV string.

    This DoFn converts a Python dict into
    a CSV string.

    Args:
      fieldnames: A list of strings representing keys of a dict.
    """

    def __init__(self, fieldnames):
        super(DictToCSVString, self).__init__()

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


class Predict(beam.DoFn):
    def __init__(self, config_path):
        from common import load_yml
        from _types import Config

        self._config = Config(**load_yml(config_path))
        super().__init__()

    def setup(self):
        self.load_model()
        return super().setup()

    def load_model(self):
        """load model"""
        from models._models import get_model
        from models.dino.utils import restart_from_checkpoint
        import os

        c = self._config
        self.model, self.linear_classifier = get_model(**c.__dict__)
        restart_from_checkpoint(
            os.path.join(c.model_head_root),
            state_dict=self.linear_classifier,
        )

    def process(self, element):
        import torch
        from datasets.ssl4eo_dataset import SSL4EO

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
        super().__init__()

    def setup(self):
        import ee
        import google.auth

        credentials, _ = google.auth.default()
        ee.Initialize(
            credentials,
            project=PROJECT,
            opt_url="https://earthengine-highvolume.googleapis.com",
        )
        return super().setup()

    def process(self, element):
        """download imagery"""
        from download_data.download_wraper import single_patch
        from pathlib import Path

        sample = element
        coords = (sample.long, sample.lat)
        local_root = Path(self.dst)
        img_root = single_patch(
            coords,
            id=sample.id,
            dst=local_root / "imgs",
            year=2019,
            bands=BANDS,
            crop_dimensions=CROPS,
        )
        yield {
            "img_root": img_root,
            "long": sample.long,
            "lat": sample.lat,
            "id": sample.id,
        }


def dict_to_row(d):
    return beam.Row(**d)


beam_options = PipelineOptions()
cols = ["id", "long", "lat", "prob_label", "pred_label"]
with beam.Pipeline() as p:
    bdf = (
        p
        | "read input data" >> ReadFromCsv(P)
        | "download imagery" >> beam.ParDo(GetImagery(dst=TMP)).with_output_types(dict)
        | "predict" >> beam.ParDo(Predict(config_path=CONFIG)).with_output_types(dict)
        # | "convert to rows" >> beam.Map(dict_to_row)
        | "to csv str" >> beam.ParDo(DictToCSVString(cols))
        # | "write to csv" >> WriteToCsv(O)  # beam.Map(print)
        | "write to csv" >> WriteToText(O, header=",".join(cols))
    )


# build your pipeline here
