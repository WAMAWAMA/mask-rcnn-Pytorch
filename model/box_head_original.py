# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved.
import torch
from torch import nn
from roi_box_feature_extractor import ROIFeatureExtractor

class ROIBoxHead(torch.nn.Module):
    """
    Generic Box Head class.
    """

    def __init__(self, loss_weights=[1, 1, 1, 1]):
        super(ROIBoxHead, self).__init__()
        self.feature_extractor = ROIFeatureExtractor()
        self.predictor = make_roi_box_predictor()
        self.post_processor = make_roi_box_post_processor()

        self.num_evaluation = len(self.post_processor)

        self.loss_evaluator = make_roi_box_loss_evaluator()

        self.conv_cls_weight = loss_weights[0]
        self.conv_reg_weight = loss_weights[1]
        self.fc_cls_weight = loss_weights[2]
        self.fc_reg_weight = loss_weights[3]


    def forward(self, features, proposals, targets=None):
        """
        Arguments:
            features (list[Tensor]): feature-maps from possibly several levels
            proposals (list[BoxList]): proposal boxes
            targets (list[BoxList], optional): the ground-truth targets.

        Returns:
            x (Tensor): the result of the feature extractor
            proposals (list[BoxList]): during training, the subsampled proposals
                are returned. During testing, the predicted boxlists are returned
            losses (dict[Tensor]): During training, returns the losses for the
                head. During testing, returns an empty dict.
        """

        if self.training:
            with torch.no_grad():
                proposals = self.loss_evaluator.subsample(proposals, targets)

        # extract features that will be fed to the final classifier. The
        # feature_extractor generally corresponds to the pooler + heads
        x = self.feature_extractor(features, proposals)
        # final classifier that converts the features into predictions
        # class_logits, box_regression = self.predictor(x)
        class_logits, box_regression, class_logits_fc, box_regression_fc = self.predictor(x)

        if not self.training:
            ## combine two results based on the level
            dtype, device = class_logits.dtype, class_logits.device
            result = []
            for i in range(self.num_evaluation):
                result_ = self.post_processor[i]((class_logits, box_regression, class_logits_fc, box_regression_fc), proposals)
                result.append(result_)
            return x, result, {}

        loss_classifier, loss_box_reg = self.loss_evaluator(
            [class_logits], [box_regression]
        )

        loss_classifier_fc, loss_box_reg_fc = self.loss_evaluator(
            [class_logits_fc], [box_regression_fc]
        )

        ## loss weights
        loss_classifier = loss_classifier * self.conv_cls_weight
        loss_box_reg = loss_box_reg * self.conv_reg_weight
        loss_classifier_fc = loss_classifier_fc * self.fc_cls_weight
        loss_box_reg_fc = loss_box_reg_fc * self.fc_reg_weight

        return (
            x,
            proposals,
            dict(loss_classifier=loss_classifier, loss_box_reg=loss_box_reg, loss_classifier_fc=loss_classifier_fc, loss_box_reg_fc=loss_box_reg_fc)
        )


def build_roi_box_head(cfg):
    """
    Constructs a new box head.
    By default, uses ROIBoxHead, but if it turns out not to be enough, just register a new class
    and make it a parameter in the config
    """
    return ROIBoxHead(cfg)