"""Provide functions for loading metabolic models over the wire."""


import gzip
from io import BytesIO
from typing import List, Union

import httpx
import pydantic

from .abstract_model_repository import AbstractModelRepository


class BioModelsFile(pydantic.BaseModel):
    """Define a single BioModels file description."""

    name: str
    size: int = pydantic.Field(alias="fileSize")


class BioModelsFilesResponse(pydantic.BaseModel):
    """Define the BioModels files JSON response."""

    main: List[BioModelsFile] = []


class BioModels(AbstractModelRepository):
    """
    Define a concrete implementation of the BioModels repository.

    Attributes
    ----------
    name : str
        The name of the BioModels repository.

    """

    name: str = "BioModels"

    def __init__(
        self,
        *,
        url: Union[str, httpx.URL] = "https://www.ebi.ac.uk/biomodels/model/",
        **kwargs,
    ):
        """
        Initialize a BioModels repository interface.

        Parameters
        ----------
        url : httpx.URL or str, optional
            The base URL from where to load the models (default
            https://www.ebi.ac.uk/biomodels/model/).

        Other Parameters
        ----------------
        kwargs
            Passed to the parent constructor in order to enable multiple inheritance.

        """
        super().__init__(url=url, **kwargs)

    def get_sbml(self, model_id: str) -> bytes:
        """
        Attempt to download an SBML document from the repository.

        Parameters
        ----------
        model_id : str
            The identifier of the desired metabolic model. This is typically repository
            specific.

        Returns
        -------
        bytes
            A gzip-compressed, UTF-8 encoded SBML document.

        Raises
        ------
        httpx.HTTPError
            In case there are any connection problems.

        """
        data = BytesIO()
        response = httpx.get(
            url=self._url.join(f"files/{model_id}"),
            headers={"Accept": "application/json"},
        )
        response.raise_for_status()
        files = BioModelsFilesResponse.parse_obj(response.json())
        is_found = False
        for model in files.main:
            if model.name.endswith("xml"):
                is_found = True
                break
        if not is_found:
            RuntimeError(f"'{model_id}' does not seem to contain an SBML document.")
        with self._progress, httpx.stream(
            method="GET",
            url=self._url.join(f"download/{model_id}"),
            params={"filename": model.name},
        ) as response:
            response.raise_for_status()
            task_id = self._progress.add_task(
                description="download",
                total=model.size,
                model_id=model_id,
            )
            for chunk in response.iter_bytes():
                data.write(chunk)
                self._progress.update(task_id=task_id, advance=len(chunk))
        data.seek(0)
        return gzip.compress(data.read())
