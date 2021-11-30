import torch
import torch.nn.functional as F
from tqdm import tqdm
from src.utils import create_dict_meters


def compute_ranks(image_embeds, text_embeds):
    image_embeds_norm = F.normalize(image_embeds, dim=1)
    text_embeds_norm = F.normalize(text_embeds, dim=1)
    sim_matrix = torch.mm(image_embeds_norm, text_embeds_norm.T)

    # For each image we have five captions the capt_index/5 corresponds to the image index
    image_inds = torch.floor_divide(torch.argsort(sim_matrix, -1), 5)
    text_inds = torch.argsort(sim_matrix.T, -1)

    image_ranks = [
        (image_inds[i] == i).nonzero().flatten() for i in range(image_inds.shape[0])
    ]
    image_ranks = torch.stack(image_ranks)

    text_ranks = [
        (text_inds[i] == i // 5).nonzero().flatten() for i in range(text_inds.shape[0])
    ]
    text_ranks = torch.stack(text_ranks)

    return image_ranks, text_ranks


def recall_k(k, image_ranks, text_ranks):
    image_recall = (image_ranks < k).sum() / image_ranks.shape[0] * 5
    text_recall = (text_ranks < k).sum() / text_ranks.shape[0]
    return image_recall, text_recall


def evaluate(image_embedder, text_embedder, loader, loss_fn, ks, device, epoch=None):
    # We will do validation on all five captions
    image_embedder.eval()
    text_embedder.eval()
    metrics = create_dict_meters(ks)
    with torch.no_grad():
        for idx, data in enumerate(loader, 0):
            # Extract positive captions
            ids = data["ids"].to(device, dtype=torch.long)
            ids = torch.flatten(ids, 0, 1)
            masks = data["mask"].to(device, dtype=torch.long)
            masks = torch.flatten(masks, 0, 1)
            # Extract images
            input_images = data["image"].to(device, dtype=torch.float)
            # Compute embeddings for images and texts
            image_embeds = image_embedder(input_images)
            text_embeds = text_embedder(ids, masks)

            loss = loss_fn(image_embeds, text_embeds)
            metrics['loss'].update(loss.item())

            image_ranks, text_ranks = compute_ranks(image_embeds, text_embeds, device)
            metrics['mr_t2i'].update(torch.mean(torch.Tensor.float(text_ranks)))
            metrics['mr_i2t'].update(torch.mean(torch.Tensor.float(image_ranks)))
            # print(
            #     "Batch {} mean rank Text2Image {} Image2Text {}\n".format(
            #         idx,
            #         metrics['mr_t2i'].val,
            #         metrics['mr_i2t'].val,
            #     )
            # )
            for k in ks:
                image_recall, text_recall = recall_k(k, image_ranks, text_ranks)
                metrics[f'r@{k}_t2i'].update(image_recall)
                metrics[f'r@{k}_i2t'].update(text_recall)
                # print(
                #     "Batch {} Recall @ {} Text2Image {} Image2Text {}\n".format(
                #         idx, k, image_recall, text_recall
                #     )
                # )
    final_metrics = ' | '.join(['{}: {%.2f}'.format(name, metrics[name].avg) for name in metrics])
    if epoch == None:
        print('Final TEST metrics | ' + final_metrics)
    else:
        print(f'VAL Epoch {epoch} | ' + final_metrics)
    return metrics