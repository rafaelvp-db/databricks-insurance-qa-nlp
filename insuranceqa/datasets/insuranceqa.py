import torch
from torch.utils.data import Dataset, DataLoader
from pyspark.storagelevel import StorageLevel
from sklearn.preprocessing import LabelEncoder
from transformers import AutoTokenizer
import itertools
import collections
from typing import List
import pandas as pd

class InsuranceDataset(Dataset):
    def __init__(
      self,
      database_name = "insuranceqa",
      split = None,
      questions: List[str] = [],
      input_col = "question_en",
      label_col = "topic_en",
      storage_level = StorageLevel.MEMORY_ONLY,
      tokenizer = "distilbert-base-uncased",
      max_length = 512
    ):
      super().__init__()
      self.input_col = input_col
      self.label_col = label_col
      self.split = split
      
      if split is not None:
        self.df = spark.sql(
          f"select * from {database_name}.{self.split}"
        ).toPandas()
        if split == "train":
          self.class_mappings = self._get_class_mappings()
      elif len(questions) > 0:
        self.df = pd.DataFrame(questions, columns = ["question_en"])
      else:
        raise ValueError("You need to pass either split or questions")
        
      self.length = len(self.df)
      self.tokenizer = AutoTokenizer.from_pretrained(tokenizer)
      self.max_length = max_length
      self.weights = None

    def _get_class_mappings(self):
      labels = self.df \
        .topic_en \
        .unique()

      indexes = LabelEncoder().fit_transform(labels)
      class_mappings = dict(zip(labels, indexes))
      return class_mappings

    def _get_class_weights(self):

      # Calculating class_weights
      if self.split == "train":
        weights_df = self.df.groupby("topic_en").count().reset_index()
        weights_df["weight"] = 1 / weights_df["id"]
        self.weights = torch.tensor(weights_df["weight"].values)

      class_mappings = training_data.class_mappings
      weights = [(class_mappings[row[1]], row[0]) for row in list(itertools.chain(spark.sql(query).toLocalIterator()))]
      weights_dict = collections.OrderedDict(sorted(dict(weights).items()))
      weights_tensor = torch.tensor([weight[1] for weight in weights_dict.items()])
      self.weights = weights_tensor

    def _encode_label(self, label):
      label_class = self.class_mappings[label]
      encoded_label = torch.nn.functional.one_hot(
        torch.tensor([label_class]),
        num_classes = len(self.class_mappings)
      )
      return encoded_label.type(torch.float)

    def __len__(self):
      return len(self.df)

    def __getitem__(self, idx):
      question = self.df.loc[idx, self.input_col]
      inputs = self.tokenizer(
        question,
        None,
        add_special_tokens=True,
        return_token_type_ids=True,
        truncation=True,
        max_length=self.max_length,
        padding="max_length"
      )

      ids = inputs['input_ids']
      mask = inputs['attention_mask']
      output = {
        "input_ids": torch.tensor(ids, dtype = torch.long),
        "attention_mask": torch.tensor(mask, dtype = torch.long)
      }
      
      if self.split == "train":
        labels = self.df.loc[idx, self.label_col]
        labels = self._encode_label(labels)[0]
        output["labels"] = labels
        
      return output